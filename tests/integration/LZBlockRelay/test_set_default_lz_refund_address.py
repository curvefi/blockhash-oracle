"""Test for LZBlockRelay set_default_lz_refund_address function."""

import pytest
import boa


@pytest.mark.mainnet
def test_set_default_lz_refund_address(forked_env, lz_block_relay, dev_deployer):
    """Test setting the default LZ refund address."""
    # Generate a non-owner address
    user = boa.env.generate_address()

    # Only owner can set refund address
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.set_default_lz_refund_address(user)

    # Owner can set refund address
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_default_lz_refund_address(user)

    assert lz_block_relay.default_lz_refund_address() == user

    # Can set to another address
    another_user = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_default_lz_refund_address(another_user)

    assert lz_block_relay.default_lz_refund_address() == another_user
