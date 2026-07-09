"""Test for ChainlinkBlockRelay _commit_block internal function."""

import pytest
import boa
from conftest import EMPTY_ADDRESS


@pytest.mark.mainnet
def test_commit_block(forked_env, chainlink_block_relay, block_oracle, dev_deployer, block_data):
    """_commit_block records a committer vote; with threshold=1 (relay as sole
    committer) the block is also confirmed immediately."""
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]

    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(chainlink_block_relay.address, True)
        chainlink_block_relay.set_block_oracle(block_oracle.address)

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.internal._commit_block(test_block_number, test_block_hash)

    # vote recorded
    assert (
        block_oracle.committer_votes(chainlink_block_relay.address, test_block_number)
        == test_block_hash
    )
    # and confirmed at threshold=1
    assert block_oracle.get_block_hash(test_block_number) == test_block_hash


@pytest.mark.mainnet
def test_commit_block_oracle_not_configured(
    forked_env, chainlink_block_relay, dev_deployer, block_data
):
    """Test that _commit_block reverts when no oracle is set."""
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_block_oracle(EMPTY_ADDRESS)

        with boa.reverts("Oracle not configured"):
            chainlink_block_relay.internal._commit_block(block_data["number"], block_data["hash"])
