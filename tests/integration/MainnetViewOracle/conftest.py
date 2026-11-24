import os

import boa
import pytest
from web3 import Web3

EMPTY_ADDRESS = boa.eval("empty(address)")
EMPTY_HASH = b"\x00" * 32

# Real deployed contract addresses on Ethereum mainnet
CCIP_ROUTER = "0x80226fc0Ee2b096224EeAc085Bb9a8cba1146f7D"
CRE_FORWARDER = "0x0b93082D9b3C7C97fAcd250082899BAcf3af3885"
LZ_ENDPOINT = "0x1a44076050125825900e736c501f859c50fE728c"
LZ_READ_CHANNEL = 4294967295
LZ_EID = 30101  # Ethereum mainnet: here the relay reads its own chain

BASE_CHAIN_SELECTOR = 15971525489660198786
CCIP_RECEIVE_GAS_LIMIT = 150_000
MAINNET_CHAIN_ID = 1

# MainnetBlockView serves [head - 8191, head - 65]. A fork only has real hashes for blocks
# older than 256, which come from the history contract's storage.
BLOCK_AGE = 1_000
NEWEST_BLOCK_AGE = 65
OLDEST_BLOCK_AGE = 8_191

EXPECTED_WORKFLOW_ID = bytes.fromhex("cc" * 32)
VALID_METADATA = EXPECTED_WORKFLOW_ID + bytes(10) + bytes(20)


def received(relay, block_number):
    """The hash the relay holds as received for a block: boa keeps a reverted write's key, with an empty value"""
    return relay._storage.received_blocks.get().get(block_number, EMPTY_HASH)


@pytest.fixture(scope="session")
def rpc_url(drpc_api_key):
    """Always fork Ethereum mainnet. MAINNET_FORK_RPC overrides the endpoint."""
    override = os.getenv("MAINNET_FORK_RPC")
    if override:
        return override
    return f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"


@pytest.fixture()
def view_oracle(forked_env, mainnet_block_view, dev_deployer):
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/MainnetViewOracle.vy", mainnet_block_view.address)


@pytest.fixture()
def head(forked_env):
    return boa.env.evm.patch.block_number


@pytest.fixture()
def block(head, rpc_url):
    """(number, hash) of a block inside the view's window, the hash taken from the node"""
    number = head - BLOCK_AGE
    return number, bytes(Web3(Web3.HTTPProvider(rpc_url)).eth.get_block(number)["hash"])


@pytest.fixture()
def chainlink_relay(view_oracle, dev_deployer):
    """ChainlinkBlockRelay on Ethereum with the view oracle in its oracle slot"""
    with boa.env.prank(dev_deployer):
        relay = boa.load("contracts/messengers/ChainlinkBlockRelay.vy", CCIP_ROUTER, EMPTY_ADDRESS)
        relay.set_block_oracle(view_oracle.address)
        relay.set_expected_workflow_id(EXPECTED_WORKFLOW_ID)
        relay.set_forwarder_address(CRE_FORWARDER)
    return relay


@pytest.fixture()
def lz_relay(view_oracle, mainnet_block_view, dev_deployer):
    """LZBlockRelay on Ethereum, reading Ethereum, with the view oracle in its oracle slot"""
    with boa.env.prank(dev_deployer):
        relay = boa.load("contracts/messengers/LZBlockRelay.vy", LZ_ENDPOINT)
        relay.set_block_oracle(view_oracle.address)
        relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
    return relay
