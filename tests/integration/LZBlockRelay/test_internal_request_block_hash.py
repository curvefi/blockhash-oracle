"""Test for LZBlockRelay _request_block_hash internal function."""

import pytest
import boa

# Constants for test
from conftest import LZ_READ_CHANNEL, LZ_EID


@pytest.mark.mainnet
def test_request_block_hash(
    forked_env, lz_block_relay, mainnet_block_view, dev_deployer, block_data
):
    """Test requesting block hash internal function."""
    # Setup the relay for testing
    with boa.env.prank(dev_deployer):
        # Configure read capability
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

        # Make sure we have funds to pay for LZ messages
        boa.env.set_balance(dev_deployer, 10**20)  # 100 ETH
        boa.env.set_balance(lz_block_relay.address, 10**20)  # 100 ETH

    # Setup broadcast targets
    test_eids = [2, 3]  # Target chain IDs
    test_fees = [10**16, 2 * 10**16]  # 0.01 ETH and 0.02 ETH fees

    # Note: In a test environment, the actual cross-chain message will not be sent,
    # but we can verify the function doesn't revert and properly caches targets
    assert lz_block_relay._storage.broadcast_targets.get() == {}
    # Call the internal request function
    with boa.env.prank(dev_deployer):
        # Request for specific block
        lz_block_relay.internal._request_block_hash(
            0,
            test_eids,
            test_fees,
            200_000,  # gas limit
            value=10**18,  # 1 ETH (should be enough for the message)
        )
    new_targets = list(lz_block_relay._storage.broadcast_targets.get().values())
    assert len(new_targets[0]) == 2

    # In a production environment, this would test that:
    # 1. LZ message is sent (measurable by checking balance change or events)
    # 2. broadcast_targets mapping is populated with correct values
