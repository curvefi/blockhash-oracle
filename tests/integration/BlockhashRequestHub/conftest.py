import os

import boa
import pytest

EMPTY_ADDRESS = boa.eval("empty(address)")

# Real deployed contracts on Ethereum mainnet
CCIP_ROUTER = "0x80226fc0Ee2b096224EeAc085Bb9a8cba1146f7D"
CRE_FORWARDER = "0x0b93082D9b3C7C97fAcd250082899BAcf3af3885"
LZ_ENDPOINT = "0x1a44076050125825900e736c501f859c50fE728c"

LZ_READ_CHANNEL = 4294967295
LZ_EID = 30101  # Ethereum mainnet, the chain being read

# Real identifiers: fake ones make the router revert on getFee/ccipSend
BASE_CHAIN_SELECTOR = 15971525489660198786
ARBITRUM_CHAIN_SELECTOR = 4949039107694359620
BASE_EID = 30184
ARBITRUM_EID = 30110

CCIP_RECEIVE_GAS_LIMIT = 150_000
LZ_RECEIVE_GAS_LIMIT = 150_000
LZ_READ_GAS_LIMIT = 100_000

# Workflow identity the relay binds onReport to, and the 62-byte Keystone metadata carrying it
EXPECTED_WORKFLOW_ID = bytes.fromhex("cc" * 32)
VALID_METADATA = EXPECTED_WORKFLOW_ID + bytes(10) + bytes(20)

# Hub configuration
BASE_FEE = 10**15
FEE_PER_TARGET = 5 * 10**14
FEE_MULTIPLIER_BPS = 25_000
BASE_ON_REPORT_GAS = 300_000
CCIP_SEND_GAS = 150_000

RAIL_LZ = 1
RAIL_CRE = 2
RAIL_BOTH = RAIL_LZ | RAIL_CRE


@pytest.fixture(scope="session")
def rpc_url(drpc_api_key):
    """Override the parent conftest: always fork Ethereum mainnet.

    MAINNET_FORK_RPC overrides the endpoint (useful when the DRPC free tier throttles).
    """
    override = os.getenv("MAINNET_FORK_RPC")
    if override:
        return override
    return f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"


@pytest.fixture()
def user():
    addr = boa.env.generate_address()
    boa.env.set_balance(addr, 10**20)
    return addr


# Deployed here rather than reusing the root block_oracle fixture: that one does not depend on
# forked_env, so requesting it first lands it in the pre-fork env, which boa.swap_env then discards.
@pytest.fixture()
def oracle(forked_env, dev_deployer):
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/BlockOracle.vy")


@pytest.fixture()
def cre_relay(oracle, dev_deployer):
    """Real ChainlinkBlockRelay against the mainnet CCIP router, with real peers."""
    with boa.env.prank(dev_deployer):
        relay = boa.load("contracts/messengers/ChainlinkBlockRelay.vy", CCIP_ROUTER, EMPTY_ADDRESS)
        relay.set_block_oracle(oracle.address)
        relay.set_expected_workflow_id(EXPECTED_WORKFLOW_ID)
        relay.set_forwarder_address(CRE_FORWARDER)
        relay.set_peers(
            [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR],
            [boa.env.generate_address(), boa.env.generate_address()],
        )
    return relay


@pytest.fixture()
def lz_relay(oracle, mainnet_block_view, dev_deployer):
    """Real LZBlockRelay against the mainnet endpoint, read-enabled so it can be requested from."""
    with boa.env.prank(dev_deployer):
        relay = boa.load("contracts/messengers/LZBlockRelay.vy", LZ_ENDPOINT)
        relay.set_block_oracle(oracle.address)
        relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
        relay.set_peers(
            [BASE_EID, ARBITRUM_EID],
            [boa.env.generate_address(), boa.env.generate_address()],
        )
    return relay


@pytest.fixture()
def hub(oracle, cre_relay, lz_relay, dev_deployer):
    """Both relays commit into one oracle at threshold 1, which the hub's constructor requires."""
    with boa.env.prank(dev_deployer):
        oracle.add_committer(cre_relay.address, False)
        oracle.add_committer(lz_relay.address, False)
        oracle.set_threshold(1)
        return boa.load(
            "contracts/BlockhashRequestHub.vy",
            oracle.address,
            lz_relay.address,
            cre_relay.address,
            BASE_FEE,
            FEE_PER_TARGET,
            FEE_MULTIPLIER_BPS,
            BASE_ON_REPORT_GAS,
            CCIP_SEND_GAS,
        )
