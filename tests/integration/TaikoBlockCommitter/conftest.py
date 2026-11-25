import os

import boa
import pytest
from eth_utils import keccak
from rlp import encode
from web3 import Web3

EMPTY_HASH = b"\x00" * 32

# Real deployed contract addresses on Taiko mainnet
SIGNAL_SERVICE = "0x1670000000000000000000000000000000000005"
ANCHOR = "0x1670000000000000000000000000000000010001"

MIN_DEPTH = 64
# Checkpoints are about 32 Ethereum blocks apart; this many numbers back hold several
CHECKPOINT_LOOKBACK = 140

HEADER_FIELDS = [
    "parentHash",
    "sha3Uncles",
    "miner",
    "stateRoot",
    "transactionsRoot",
    "receiptsRoot",
    "logsBloom",
    "difficulty",
    "number",
    "gasLimit",
    "gasUsed",
    "timestamp",
    "extraData",
    "mixHash",
    "nonce",
]
OPTIONAL_HEADER_FIELDS = [
    "baseFeePerGas",
    "withdrawalsRoot",
    "blobGasUsed",
    "excessBlobGas",
    "parentBeaconBlockRoot",
    "requestsHash",
]


def encode_header(block):
    """RLP header of a block as a node returns it, checked against the block's hash"""
    fields = [block[key] for key in HEADER_FIELDS]
    fields += [block[key] for key in OPTIONAL_HEADER_FIELDS if block.get(key) is not None]
    fields[2] = bytes.fromhex(fields[2][2:])  # the miner comes as a string
    header = encode([field if isinstance(field, int) else bytes(field) for field in fields])
    assert keccak(header) == bytes(block["hash"]), f"header fields changed: {sorted(block)}"
    return header


@pytest.fixture(scope="session")
def rpc_url(chains, drpc_api_key):
    """Always fork Taiko. TAIKO_FORK_RPC overrides the endpoint."""
    override = os.getenv("TAIKO_FORK_RPC")
    if override:
        return override
    chain = chains["taiko"]
    return chain["drpc"] + drpc_api_key if drpc_api_key else chain["rpc"]


@pytest.fixture(scope="session")
def ethereum(drpc_api_key):
    """Ethereum itself, to compare against. MAINNET_FORK_RPC overrides the endpoint."""
    override = os.getenv("MAINNET_FORK_RPC")
    url = override or f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"
    return Web3(Web3.HTTPProvider(url))


@pytest.fixture()
def ethereum_headers(ethereum):
    """Headers of `count` Ethereum blocks from `start` downwards: they prove block start - count"""

    def headers(start, count):
        return [encode_header(ethereum.eth.get_block(start - i)) for i in range(count)]

    return headers


@pytest.fixture()
def signal_service(forked_env):
    return boa.loads_abi(
        """[{"name": "getCheckpoint", "type": "function", "stateMutability": "view",
        "inputs": [{"name": "_blockNumber", "type": "uint48"}],
        "outputs": [{"type": "tuple", "components": [
            {"name": "blockNumber", "type": "uint48"},
            {"name": "blockHash", "type": "bytes32"},
            {"name": "stateRoot", "type": "bytes32"}]}]}]"""
    ).at(SIGNAL_SERVICE)


@pytest.fixture()
def anchor_block(forked_env):
    """The latest Ethereum block Taiko holds"""
    anchor = boa.loads_abi(
        """[{"name": "getBlockState", "type": "function", "stateMutability": "view", "inputs": [],
        "outputs": [{"type": "tuple", "components": [
            {"name": "anchorBlockNumber", "type": "uint48"},
            {"name": "ancestorsHash", "type": "bytes32"}]}]}]"""
    ).at(ANCHOR)
    return anchor.getBlockState()[0]


@pytest.fixture()
def checkpoints(signal_service, anchor_block):
    """Ethereum blocks Taiko holds a checkpoint for, newest first"""
    found = []
    for number in range(anchor_block, anchor_block - CHECKPOINT_LOOKBACK, -1):
        try:
            signal_service.getCheckpoint(number)
            found.append(number)
        except boa.BoaError:
            pass
    return found


@pytest.fixture()
def old_checkpoint(checkpoints, anchor_block):
    """The newest checkpoint deep enough to be committed as it is"""
    return next(number for number in checkpoints if number + MIN_DEPTH <= anchor_block)


@pytest.fixture()
def committer(forked_env, block_oracle, block_headers_decoder, dev_deployer):
    """TaikoBlockCommitter as the only committer of a fresh oracle, with a header verifier set"""
    with boa.env.prank(dev_deployer):
        committer = boa.load(
            "contracts/native/TaikoBlockCommitter.vy", block_oracle.address, SIGNAL_SERVICE, ANCHOR
        )
        block_oracle.add_committer(committer.address, True)
        block_oracle.set_header_verifier(block_headers_decoder.address)
    return committer
