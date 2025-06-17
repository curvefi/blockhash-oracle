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

    # Enable the same channel again - should be idempotent (no error)
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
    
    # State should remain the same
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

    # Disable when already disabled - should be idempotent (no error)
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(False, LZ_READ_CHANNEL, 0, EMPTY_ADDRESS)
    
    # State should remain the same
    assert not lz_block_relay.read_enabled()
    assert lz_block_relay.mainnet_eid() == 0
    assert lz_block_relay.mainnet_block_view() == EMPTY_ADDRESS


@pytest.mark.mainnet
def test_set_read_config_channel_switch(forked_env, lz_block_relay, mainnet_block_view, dev_deployer):
    """Test switching between different read channels."""
    # Enable first channel
    first_channel = LZ_READ_CHANNEL
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, first_channel, LZ_EID, mainnet_block_view.address)
    
    assert lz_block_relay.read_enabled()
    assert lz_block_relay.read_channel() == first_channel
    
    # Switch to a different channel
    second_channel = LZ_READ_CHANNEL - 1000
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, second_channel, LZ_EID, mainnet_block_view.address)
    
    assert lz_block_relay.read_enabled()
    assert lz_block_relay.read_channel() == second_channel
    
    # Verify the old channel peer has been cleared
    # The first channel should no longer have a peer set
    assert lz_block_relay.peers(first_channel) == b'\x00' * 32
    
    # The new channel should have the contract itself as the peer
    # Convert address to bytes32 format (20 bytes address padded to 32 bytes)
    address_bytes = bytes.fromhex(lz_block_relay.address[2:])  # Remove '0x' prefix
    expected_peer = b'\x00' * 12 + address_bytes  # Left pad with zeros to make 32 bytes
    assert lz_block_relay.peers(second_channel) == expected_peer


@pytest.mark.mainnet
def test_set_read_config_reenable_same_channel(forked_env, lz_block_relay, mainnet_block_view, dev_deployer):
    """Test re-enabling the same channel after disabling."""
    # Enable channel
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
    
    address_bytes = bytes.fromhex(lz_block_relay.address[2:])  # Remove '0x' prefix
    expected_peer = b'\x00' * 12 + address_bytes  # Left pad with zeros to make 32 bytes
    assert lz_block_relay.peers(LZ_READ_CHANNEL) == expected_peer
    
    # Disable
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(False, LZ_READ_CHANNEL, 0, EMPTY_ADDRESS)
    
    # Peer should be cleared
    assert lz_block_relay.peers(LZ_READ_CHANNEL) == b'\x00' * 32
    
    # Re-enable with the same channel
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
    
    # Peer should be set again
    assert lz_block_relay.peers(LZ_READ_CHANNEL) == expected_peer
