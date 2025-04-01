"""Test for LZBlockRelay _get_gas_limit internal function."""

import pytest
import boa


@pytest.mark.mainnet
def test_get_gas_limit(forked_env, lz_block_relay, dev_deployer):
    """Test getting gas limit for a given EID."""
    # Default gas limit should already be set in the contract init
    default_gas_limit = 100_000
    assert lz_block_relay.eval("self._get_gas_limit(0)") == default_gas_limit

    # Set specific gas limits for some chains
    test_eids = [1, 2, 3]
    test_gas_limits = [600000, 700000, 800000]

    with boa.env.prank(dev_deployer):
        lz_block_relay.set_gas_limits(test_eids, test_gas_limits)

    # Verify specific gas limits
    for i, eid in enumerate(test_eids):
        assert lz_block_relay.eval("self._get_gas_limit(%s)" % eid) == test_gas_limits[i]

    # Chain without specific gas limit should use default
    assert lz_block_relay.eval("self._get_gas_limit(999)") == default_gas_limit
