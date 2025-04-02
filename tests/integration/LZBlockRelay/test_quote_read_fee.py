"""Test for LZBlockRelay quote_read_fee function."""

import pytest
import boa

# Constants for test
from conftest import LZ_READ_CHANNEL, LZ_EID


@pytest.mark.mainnet
def test_quote_read_fee(forked_env, lz_block_relay, mainnet_block_view, dev_deployer):
    """Test quoting a fee for reading a block hash."""
    # Should fail if read not enabled initially
    with boa.reverts("Read not enabled - call set_read_config"):
        lz_block_relay.quote_read_fee(100_000, 0)

    # Enable read functionality
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

    # Quote with default parameters
    fee = lz_block_relay.quote_read_fee(100_000, 0)
    assert isinstance(fee, int)

    # Quote with value for return message
    fee_with_value = lz_block_relay.quote_read_fee(300_000, 10**17)
    assert isinstance(fee_with_value, int)

    # Quote for specific block number
    fee_specific_block = lz_block_relay.quote_read_fee(300_000, 10**17, 14000000)
    assert isinstance(fee_specific_block, int)
