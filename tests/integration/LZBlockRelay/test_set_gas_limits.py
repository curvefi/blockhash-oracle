"""Test for LZBlockRelay set_gas_limits function."""

import pytest
import boa


@pytest.mark.mainnet
def test_set_gas_limit(forked_env, lz_block_relay, dev_deployer):
    """Test setting gas limits for different chains."""
    test_gas_limit = 600000

    # Generate a non-owner address
    user = boa.env.generate_address()

    # Only owner can set gas limits
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.set_gas_limit(test_gas_limit)

    # Owner can set gas limits
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_gas_limit(test_gas_limit)

    # Verify gas limits were set correctly
    assert lz_block_relay.eval("self.lz_receive_gas_limit") == test_gas_limit
