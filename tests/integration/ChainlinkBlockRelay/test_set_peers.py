"""Test for ChainlinkBlockRelay batched set_peers function."""

import pytest
import boa


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
