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


@pytest.fixture()
def chainlink_block_relay(forked_env, dev_deployer):
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/messengers/ChainlinkBlockRelay.vy", CCIP_ROUTER, CRE_FORWARDER)


@pytest.fixture()
def configured_relay(chainlink_block_relay, block_oracle, dev_deployer):
    """Relay with oracle, committer, and CRE forwarder fully configured."""
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_block_oracle(block_oracle.address)
        block_oracle.add_committer(chainlink_block_relay.address, True)
    return chainlink_block_relay
