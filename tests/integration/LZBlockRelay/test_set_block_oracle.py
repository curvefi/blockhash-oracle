"""Test for LZBlockRelay set_block_oracle function."""

import pytest
import boa
from conftest import EMPTY_ADDRESS


@pytest.mark.mainnet
def test_set_block_oracle(forked_env, lz_block_relay, block_oracle, dev_deployer):
    """Test setting the block oracle."""
    # Generate a non-owner address
    user = boa.env.generate_address()

    # Only owner can set block oracle
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.set_block_oracle(block_oracle.address)

    # Owner can set block oracle
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_block_oracle(block_oracle.address)

    assert lz_block_relay.block_oracle() == block_oracle.address

    # Can set to zero address to disable
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_block_oracle(EMPTY_ADDRESS)

    assert lz_block_relay.block_oracle() == EMPTY_ADDRESS
