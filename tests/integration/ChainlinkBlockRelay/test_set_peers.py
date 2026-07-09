"""Test for ChainlinkBlockRelay set_peer and set_peers functions."""

import pytest
import boa


@pytest.mark.mainnet
def test_set_peer(forked_env, chainlink_block_relay, dev_deployer):
    """Owner can set a single peer (non-owner reverts); it registers both sender
    and receiver under the selector and can be overwritten by setting again."""
    test_selector = 5009297550715157269  # Ethereum mainnet CCIP selector
    test_address = boa.env.generate_address()
    user = boa.env.generate_address()

    # only owner can set peer
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            chainlink_block_relay.set_peer(test_selector, test_address)

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_peer(test_selector, test_address)

    # both receiver and sender registered under the same selector
    assert chainlink_block_relay.selector_to_receiver(test_selector) == test_address
    assert chainlink_block_relay.selector_to_sender(test_selector) == test_address

    # setting again overwrites both
    new_address = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_peer(test_selector, new_address)
    assert chainlink_block_relay.selector_to_receiver(test_selector) == new_address
    assert chainlink_block_relay.selector_to_sender(test_selector) == new_address


@pytest.mark.mainnet
def test_set_peers(forked_env, chainlink_block_relay, dev_deployer):
    """Test setting multiple peers in batch."""
    test_selectors = [111, 222, 333]
    test_addresses = [
        boa.env.generate_address(),
        boa.env.generate_address(),
        boa.env.generate_address(),
    ]
    user = boa.env.generate_address()

    # Only owner can set peers
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            chainlink_block_relay.set_peers(test_selectors, test_addresses)

    # Owner can set peers
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_peers(test_selectors, test_addresses)

    for selector, address in zip(test_selectors, test_addresses):
        assert chainlink_block_relay.selector_to_receiver(selector) == address
        assert chainlink_block_relay.selector_to_sender(selector) == address

    # Mismatched array lengths revert
    with boa.env.prank(dev_deployer):
        with boa.reverts("Invalid peer arrays"):
            chainlink_block_relay.set_peers(test_selectors, test_addresses[:2])
