"""Test for LZBlockRelay set_gas_limits function."""

import pytest
import boa


@pytest.mark.mainnet
def test_set_gas_limits(forked_env, lz_block_relay, dev_deployer):
    """Test setting gas limits for different chains."""
    test_eids = [1, 2, 3]
    test_gas_limits = [600000, 700000, 800000]

    # Generate a non-owner address
    user = boa.env.generate_address()

    # Only owner can set gas limits
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.set_gas_limits(test_eids, test_gas_limits)

    # Owner can set gas limits
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_gas_limits(test_eids, test_gas_limits)

    # Verify gas limits were set correctly
    for i, eid in enumerate(test_eids):
        assert lz_block_relay.eval("self.gas_limit_map[%s]" % eid) == test_gas_limits[i]

    # unset must be 0
    assert lz_block_relay.eval("self.gas_limit_map[999]") == 0

    # Test with mismatched array lengths
    with boa.env.prank(dev_deployer):
        with boa.reverts("Invalid gas limit arrays"):
            lz_block_relay.set_gas_limits(test_eids, test_gas_limits[:2])
