"""Test for LZBlockRelay set_read_config function."""

import pytest
import boa
from conftest import LZ_READ_CHANNEL, LZ_EID, EMPTY_ADDRESS


@pytest.mark.mainnet
def test_set_read_config(forked_env, lz_block_relay, mainnet_block_view, dev_deployer):
    """Test setting read configuration."""
    # Generate a non-owner address
    user = boa.env.generate_address()

    # Only owner can set read config
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.set_read_config(
                True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address
            )

    # Invalid read channel
    with boa.env.prank(dev_deployer):
        with boa.reverts("Invalid read channel"):
            lz_block_relay.set_read_config(True, 1000, LZ_EID, mainnet_block_view.address)

    # Invalid config (enabled but missing parameters)
    with boa.env.prank(dev_deployer):
        with boa.reverts("Invalid read config"):
            lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, 10, EMPTY_ADDRESS)

    # Invalid config (disabled but has parameters)
    with boa.env.prank(dev_deployer):
        with boa.reverts("Invalid read config"):
            lz_block_relay.set_read_config(
                False, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address
            )

    # Valid config - enable read
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

    assert lz_block_relay.read_enabled()
    assert lz_block_relay.read_channel() == LZ_READ_CHANNEL
    assert lz_block_relay.mainnet_eid() == LZ_EID
    assert lz_block_relay.mainnet_block_view() == mainnet_block_view.address

    # Valid config - disable read
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(False, LZ_READ_CHANNEL, 0, EMPTY_ADDRESS)

    assert not lz_block_relay.read_enabled()
    assert lz_block_relay.mainnet_eid() == 0
    assert lz_block_relay.mainnet_block_view() == EMPTY_ADDRESS
