"""Package a CRE workflow artifact and compute or verify its on-chain workflow ID.

    workflow_id.py package --wasm build/binary.wasm --out binary.wasm.br.b64
    workflow_id.py id      --binary binary.wasm.br.b64 --config config.testnets.json --name ...
    workflow_id.py verify  --name blockhash-relay-testnets

The ID is sha256(owner ++ name ++ brotli-bytes ++ config ++ secretsURL) with byte 0 forced to 0x00,
where brotli-bytes is the base64 decode of the hosted artifact. Nodes recompute it from the artifacts
they fetch and refuse to start on a mismatch, so it must be computed over the bytes as SERVED - on
Windows a CRLF working copy of the config hashes differently from the LF blob GitHub returns.
"""

import argparse
import base64
import hashlib
import json
import pathlib
import sys
import urllib.request

from eth_abi import decode, encode
from eth_utils import keccak

REGISTRY = "0x4Ac54353FA4Fa961AfcC5ec4B118596d3305E7e5"  # WorkflowRegistry 2.0.0, ethereum mainnet
OWNER = "0x7589D6DADA352B798809278e5A0F8606b6088952"
RPC = "https://ethereum-rpc.publicnode.com"
BROTLI_QUALITY = (
    11  # part of the artifact's identity: other settings give different bytes and a different ID
)

WORKFLOW_VIEW = "(bytes32,address,uint64,uint8,string,string,string,string,bytes,string)"


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "curve-blockhash-oracle/ci"}),
        timeout=120,
    ).read()


def compute(owner: str, name: str, binary_b64: bytes, config: bytes, secrets_url: str = "") -> str:
    digest = hashlib.sha256()
    digest.update(bytes.fromhex(owner.removeprefix("0x")))
    digest.update(name.encode())
    digest.update(base64.b64decode(binary_b64))
    digest.update(config)
    digest.update(secrets_url.encode())
    return "0x00" + digest.digest()[1:].hex()


def registry_get(owner: str, name: str, tag: str, rpc: str):
    data = keccak(text="getWorkflow(address,string,string)")[:4] + encode(
        ["address", "string", "string"], [owner, name, tag]
    )
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": REGISTRY, "data": "0x" + data.hex()}, "latest"],
        }
    ).encode()
    req = urllib.request.Request(
        rpc, data=body, headers={"Content-Type": "application/json", "User-Agent": "curve/ci"}
    )
    result = json.load(urllib.request.urlopen(req, timeout=120))
    if "error" in result:
        sys.exit(f"registry call failed: {result['error']}")
    return decode([WORKFLOW_VIEW], bytes.fromhex(result["result"][2:]))[0]


def cmd_package(args):
    import brotli  # only the release job needs it

    raw = pathlib.Path(args.wasm).read_bytes()
    packed = base64.b64encode(brotli.compress(raw, quality=BROTLI_QUALITY))
    pathlib.Path(args.out).write_bytes(packed)
    assert brotli.decompress(base64.b64decode(packed)) == raw, "brotli roundtrip failed"
    print(f"wasm      {len(raw):,} bytes  sha256 {hashlib.sha256(raw).hexdigest()}")
    print(f"artifact  {len(packed):,} bytes  sha256 {hashlib.sha256(packed).hexdigest()}")
    print(f"written   {args.out}")


def cmd_id(args):
    binary = pathlib.Path(args.binary).read_bytes()
    config = pathlib.Path(args.config).read_bytes()
    if b"\r\n" in config:
        print(
            "WARNING: config contains CRLF; GitHub serves LF and the ID would not match",
            file=sys.stderr,
        )
    print(compute(args.owner, args.name, binary, config))


def cmd_urls(args):
    print(compute(args.owner, args.name, fetch(args.binary_url), fetch(args.config_url)))


def cmd_verify(args):
    tag = args.tag or args.name
    view = registry_get(args.owner, args.name, tag, args.rpc)
    registered = "0x" + view[0].hex()
    binary_url, config_url, status = view[5], view[6], view[3]

    print(f"workflow   {args.name} (tag {tag})")
    print(f"registered {registered}   status {status}")
    print(f"binary     {binary_url}")
    print(f"config     {config_url}")

    try:
        recomputed = compute(args.owner, args.name, fetch(binary_url), fetch(config_url))
    except Exception as exc:  # a dead URL is the failure this job exists to catch
        sys.exit(f"\nFAIL: could not fetch the registered artifacts: {type(exc).__name__} {exc}")

    print(f"recomputed {recomputed}")
    if recomputed != registered:
        sys.exit("\nFAIL: the artifacts served do not hash to the registered workflow ID")
    print("\nOK: the registry, the hosted artifacts and the workflow ID agree")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    # on the subparsers, not the top level, so they are accepted after the subcommand
    ident = argparse.ArgumentParser(add_help=False)
    ident.add_argument("--owner", default=OWNER)
    ident.add_argument("--name", default="blockhash-relay-testnets")

    sp = sub.add_parser("package", help="brotli + base64 a built wasm into the hostable artifact")
    sp.add_argument("--wasm", required=True)
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_package)

    sp = sub.add_parser("id", help="compute the workflow ID from local files", parents=[ident])
    sp.add_argument("--binary", required=True)
    sp.add_argument("--config", required=True)
    sp.set_defaults(func=cmd_id)

    sp = sub.add_parser("urls", help="compute the workflow ID from hosted URLs", parents=[ident])
    sp.add_argument("--binary-url", required=True)
    sp.add_argument("--config-url", required=True)
    sp.set_defaults(func=cmd_urls)

    sp = sub.add_parser(
        "verify", help="check the live registry against what its URLs serve", parents=[ident]
    )
    sp.add_argument("--tag")
    sp.add_argument("--rpc", default=RPC)
    sp.set_defaults(func=cmd_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
