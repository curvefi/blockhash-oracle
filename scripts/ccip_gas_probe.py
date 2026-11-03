"""Measure ChainlinkBlockRelay.ccipReceive gas on each chain's own node.

The CCIP receive gas limit is one number shared by every destination (README, "CCIP receive gas
limit"). Re-run this before adding a destination chain, or after a chain reprices opcodes, and
update the README table.

The relay, BlockOracle and a meter contract are injected with eth_call state overrides, so each
chain's client prices the execution with its own gas schedule. The meter plays the CCIP router:
it calls ccipReceive and returns the gas the call consumed.

    uv run --env-file .env python scripts/ccip_gas_probe.py [chain ...]

DRPC_API_KEY is used when set; each chain also has public fallbacks. An RPC that ignores state
overrides (seen on Etherlink) cannot be measured this way.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address

REPO = Path(__file__).resolve().parents[1]

RELAY = to_checksum_address("0x" + "11" * 20)
ORACLE = to_checksum_address("0x" + "22" * 20)
METER = to_checksum_address("0x" + "33" * 20)
PEER = to_checksum_address("0x" + "44" * 20)
OTHER_COMMITTER = to_checksum_address("0x" + "55" * 20)  # the other rail's relay
SRC_SELECTOR = 5009297550715157269  # ethereum-mainnet
BLOCK_NUMBER = 21_000_000
BLOCK_HASH = bytes.fromhex("ab" * 32)

# Storage slots from `vyper -f layout`; re-check them if either contract's storage changes
RELAY_ROUTER_SLOT = 5
RELAY_SENDERS_SLOT = 7
RELAY_ORACLE_SLOT = 8
ORACLE_BLOCK_HASH_SLOT = 1
ORACLE_LAST_CONFIRMED_SLOT = 2
ORACLE_COMMITTERS_SLOT = 11  # DynArray: length here, elements from the next slot
ORACLE_IS_COMMITTER_SLOT = 44
ORACLE_VOTES_SLOT = 45
ORACLE_THRESHOLD_SLOT = 46

METER_SRC = """# pragma version 0.4.3
@external
def measure(target: address, data: Bytes[1024]) -> (bool, uint256):
    g: uint256 = msg.gas
    ok: bool = raw_call(target, data, revert_on_failure=False)
    return ok, g - msg.gas
"""

# The oracle state the relay's vote lands in; two committers, the relay and the other rail
SCENARIOS = {
    # threshold 2, nobody voted yet: the vote is recorded, no apply
    "first_vote": {"threshold": 2, "other_voted": False, "applied": False},
    # threshold 2, the other rail already voted: this vote applies the block
    "completing_vote": {"threshold": 2, "other_voted": True, "applied": False},
    # threshold 1: this vote alone applies the block
    "sole_vote_applies": {"threshold": 1, "other_voted": False, "applied": False},
    # block already applied with this hash: _commit_block returns early
    "already_applied": {"threshold": 2, "other_voted": False, "applied": True},
}

# chain: (drpc network name, [public fallbacks])
CHAINS = {
    "ethereum": ("ethereum", ["https://ethereum-rpc.publicnode.com"]),
    "arbitrum": ("arbitrum", ["https://arb1.arbitrum.io/rpc"]),
    "avalanche": ("avalanche", ["https://api.avax.network/ext/bc/C/rpc"]),
    "base": ("base", ["https://mainnet.base.org"]),
    "bsc": ("bsc", ["https://bsc-dataseed.bnbchain.org"]),
    "celo": ("celo", ["https://forno.celo.org"]),
    "etherlink": ("etherlink", ["https://node.mainnet.etherlink.com"]),
    "fraxtal": ("fraxtal", ["https://rpc.frax.com"]),
    "gnosis": ("gnosis", ["https://rpc.gnosischain.com"]),
    "hyperliquid": ("hyperliquid", ["https://rpc.hyperliquid.xyz/evm"]),
    "ink": ("ink", ["https://rpc-gel.inkonchain.com"]),
    "mantle": ("mantle", ["https://rpc.mantle.xyz"]),
    "monad": ("monad-mainnet", ["https://rpc.monad.xyz"]),
    "corn": ("corn-mainnet", ["https://21000000.rpc.thirdweb.com"]),
    "optimism": ("optimism", ["https://mainnet.optimism.io"]),
    "plasma": ("plasma", ["https://rpc.plasma.to"]),
    "plume": ("plume", ["https://rpc.plume.org"]),
    "polygon": ("polygon", ["https://polygon-rpc.com"]),
    "sonic": ("sonic", ["https://rpc.soniclabs.com"]),
    "tac": ("tac", ["https://rpc.tac.build"]),
    "taiko": ("taiko", ["https://rpc.mainnet.taiko.xyz"]),
    "unichain": ("unichain", ["https://mainnet.unichain.org"]),
    "xdc": ("xdc", ["https://erpc.xinfin.network"]),
    "xlayer": ("xlayer", ["https://rpc.xlayer.tech"]),
}


def word(x) -> bytes:
    if isinstance(x, bytes):
        return x.rjust(32, b"\0")
    if isinstance(x, str):
        return bytes.fromhex(x[2:]).rjust(32, b"\0")
    return x.to_bytes(32, "big")


def hashmap_slot(slot, *keys) -> int:
    """Vyper 0.4 HashMap slot: keccak256(slot ++ key), nested left to right."""
    s = word(slot)
    for k in keys:
        s = keccak(s + word(k))
    return int.from_bytes(s, "big")


def runtime_code(path: Path) -> str:
    vyper = REPO / ".venv" / ("Scripts/vyper.exe" if os.name == "nt" else "bin/vyper")
    out = subprocess.run(
        [str(vyper), "-f", "bytecode_runtime", str(path)], capture_output=True, text=True, cwd=REPO
    )
    if out.returncode:
        sys.exit(out.stderr)
    return "0x" + out.stdout.strip().removeprefix("0x")


def storage(scenario) -> dict:
    relay = {
        RELAY_ROUTER_SLOT: int(METER, 16),
        RELAY_ORACLE_SLOT: int(ORACLE, 16),
        hashmap_slot(RELAY_SENDERS_SLOT, SRC_SELECTOR): int(PEER, 16),
    }
    oracle = {
        ORACLE_COMMITTERS_SLOT: 2,
        ORACLE_COMMITTERS_SLOT + 1: int(RELAY, 16),
        ORACLE_COMMITTERS_SLOT + 2: int(OTHER_COMMITTER, 16),
        hashmap_slot(ORACLE_IS_COMMITTER_SLOT, RELAY): 1,
        hashmap_slot(ORACLE_IS_COMMITTER_SLOT, OTHER_COMMITTER): 1,
        ORACLE_THRESHOLD_SLOT: scenario["threshold"],
        # a live oracle has confirmed blocks before, so this slot is not fresh
        ORACLE_LAST_CONFIRMED_SLOT: BLOCK_NUMBER - 100,
    }
    if scenario["other_voted"]:
        oracle[hashmap_slot(ORACLE_VOTES_SLOT, OTHER_COMMITTER, BLOCK_NUMBER)] = int.from_bytes(
            BLOCK_HASH, "big"
        )
    if scenario["applied"]:
        oracle[hashmap_slot(ORACLE_BLOCK_HASH_SLOT, BLOCK_NUMBER)] = int.from_bytes(
            BLOCK_HASH, "big"
        )
    return {RELAY: relay, ORACLE: oracle}


def overrides(codes, scenario):
    out = {a: {"code": c} for a, c in codes.items()}
    if scenario is not None:
        for addr, slots in storage(scenario).items():
            out[addr]["stateDiff"] = {
                "0x" + s.to_bytes(32, "big").hex(): "0x" + v.to_bytes(32, "big").hex()
                for s, v in slots.items()
            }
    return out


def measure_calldata(target, data) -> bytes:
    return keccak(b"measure(address,bytes)")[:4] + encode(["address", "bytes"], [target, data])


def ccip_receive_calldata() -> bytes:
    message = (
        bytes(32),
        SRC_SELECTOR,
        encode(["address"], [PEER]),
        encode(["uint256", "bytes32"], [BLOCK_NUMBER, BLOCK_HASH]),
        [],
    )
    sig = keccak(b"ccipReceive((bytes32,uint64,bytes,bytes,(address,uint256)[]))")[:4]
    return sig + encode(["(bytes32,uint64,bytes,bytes,(address,uint256)[])"], [message])


def eth_call(url, data, ovr) -> bytes:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": METER, "data": "0x" + data.hex(), "gas": hex(3_000_000)}, "latest", ovr],
    }
    j = requests.post(url, json=body, timeout=25).json()
    if "error" in j:
        raise RuntimeError(str(j["error"])[:160])
    return bytes.fromhex(j["result"][2:])


def measure_chain(chain, codes, key):
    name, public = CHAINS[chain]
    endpoints = ([f"https://lb.drpc.org/ogrpc?network={name}&dkey={key}"] if key else []) + public
    error = None
    for url in endpoints:
        try:
            # The meter calling a codeless address: overrides and the meter itself work here
            ok, _ = decode(
                ["bool", "uint256"],
                eth_call(url, measure_calldata(PEER, b""), overrides(codes, None)),
            )
            assert ok
            row = {}
            for name_, scenario in SCENARIOS.items():
                ok, gas = decode(
                    ["bool", "uint256"],
                    eth_call(
                        url,
                        measure_calldata(RELAY, ccip_receive_calldata()),
                        overrides(codes, scenario),
                    ),
                )
                row[name_] = gas if ok else f"reverted after {gas}"
            return row
        except Exception as e:  # next endpoint
            error = f"{url.split('/')[2]}: {e}"
            if key:  # request errors can echo the full URL, key included
                error = error.replace(key, "<key>")
            error = error[:160]
    return {"error": error}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        meter = Path(tmp) / "Meter.vy"
        meter.write_text(METER_SRC)
        codes = {
            RELAY: runtime_code(REPO / "contracts/messengers/ChainlinkBlockRelay.vy"),
            ORACLE: runtime_code(REPO / "contracts/BlockOracle.vy"),
            METER: runtime_code(meter),
        }
    key = os.getenv("DRPC_API_KEY", "")
    for chain in sys.argv[1:] or CHAINS:
        print(chain, json.dumps(measure_chain(chain, codes, key)), flush=True)


if __name__ == "__main__":
    main()
