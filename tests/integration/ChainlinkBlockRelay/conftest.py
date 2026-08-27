import os

import boa
import pytest

EMPTY_ADDRESS = boa.eval("empty(address)")

# Real deployed contract addresses on Ethereum mainnet
CCIP_ROUTER = "0x80226fc0Ee2b096224EeAc085Bb9a8cba1146f7D"
CRE_FORWARDER = "0x0b93082D9b3C7C97fAcd250082899BAcf3af3885"

# Real CCIP chain selectors for tests that trigger outbound ccipSend calls.
# Fake selectors (e.g. 111) cause the real router to revert; use these instead.
BASE_CHAIN_SELECTOR = 15971525489660198786  # Base mainnet
ARBITRUM_CHAIN_SELECTOR = 4949039107694359620  # Arbitrum One mainnet

# Default gas limit for ccipReceive on the destination chain
CCIP_RECEIVE_GAS_LIMIT = 150_000

# Workflow identity bound by configured_relay (strict onReport enforcement requires one).
# 62-byte Keystone metadata carrying just this workflow id (name/owner zeroed).
EXPECTED_WORKFLOW_ID = bytes.fromhex("cc" * 32)
VALID_METADATA = EXPECTED_WORKFLOW_ID + bytes(10) + bytes(20)


@pytest.fixture(scope="session")
def rpc_url(drpc_api_key):
    """Override parent conftest's rpc_url: always fork Ethereum mainnet.

    MAINNET_FORK_RPC overrides the endpoint (useful when the DRPC free tier throttles).
    """
    override = os.getenv("MAINNET_FORK_RPC")
    if override:
        return override
    return f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"


@pytest.fixture()
def cre_forwarder():
    """CRE Forwarder address that configured_relay trusts for onReport."""
    return CRE_FORWARDER


@pytest.fixture()
def chainlink_block_relay(forked_env, dev_deployer):
    """Base relay deployed with CRE disabled; forwarder enabled later (see configured_relay)."""
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/messengers/ChainlinkBlockRelay.vy", CCIP_ROUTER, EMPTY_ADDRESS)


@pytest.fixture()
def configured_relay(chainlink_block_relay, block_oracle, dev_deployer):
    """Relay with oracle, committer, CRE forwarder, and workflow identity configured.

    Identity is set before the forwarder is enabled (strict onReport requires it).
    """
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_block_oracle(block_oracle.address)
        chainlink_block_relay.set_expected_workflow_id(EXPECTED_WORKFLOW_ID)
        chainlink_block_relay.set_forwarder_address(CRE_FORWARDER)
        block_oracle.add_committer(chainlink_block_relay.address, True)
    return chainlink_block_relay
