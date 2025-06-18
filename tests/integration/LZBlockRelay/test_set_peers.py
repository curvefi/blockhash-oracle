"""Test for LZBlockRelay set_peers function."""

import pytest
import boa


@pytest.mark.mainnet
def test_set_peers(forked_env, lz_block_relay, dev_deployer):
    """Test setting peers for different chains."""
    test_eids = [1, 2, 3]
    test_addresses = [
        boa.env.generate_address(),
        boa.env.generate_address(),
        boa.env.generate_address(),
    ]

    # Generate a non-owner address
    user = boa.env.generate_address()

    # Only owner can set peers
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.set_peers(test_eids, test_addresses)

    # Owner can set peers
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers(test_eids, test_addresses)

    # Test with mismatched array lengths
    with boa.env.prank(dev_deployer):
        with boa.reverts("Invalid peer arrays"):
            lz_block_relay.set_peers(test_eids, test_addresses[:2])
