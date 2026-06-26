"""Test for ChainlinkBlockRelay initialization."""

import pytest
from conftest import EMPTY_ADDRESS, CCIP_ROUTER


@pytest.mark.mainnet
def test_initialization(forked_env, chainlink_block_relay, dev_deployer):
    """Test initialization of the contract."""
    assert chainlink_block_relay.owner() == dev_deployer
    assert chainlink_block_relay.router() == CCIP_ROUTER

    # Block oracle should not be configured initially
    assert chainlink_block_relay.block_oracle() == EMPTY_ADDRESS

    # Forwarder address starts unset — onReport is disabled until set_forwarder_address is called
    assert chainlink_block_relay.forwarder_address() == EMPTY_ADDRESS
