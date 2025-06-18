"""Test for LZBlockRelay _commit_block internal function."""

import pytest
import boa
from eth_utils import to_bytes
from conftest import EMPTY_ADDRESS


def _to_bytes32(value):
    """Convert a value to bytes32."""
    if isinstance(value, str) and value.startswith("0x"):
        return to_bytes(hexstr=value).rjust(32, b"\x00")
    else:
        return to_bytes(text=str(value)).rjust(32, b"\x00")


@pytest.mark.mainnet
def test_commit_block(forked_env, lz_block_relay, block_oracle, dev_deployer, block_data):
    """Test committing block hash to oracle."""
    # Add the relay as a committer to the oracle
    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(lz_block_relay.address, True)
        # Set the block oracle address in relay
        lz_block_relay.set_block_oracle(block_oracle.address)

    # Test with oracle not configured
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_block_oracle(EMPTY_ADDRESS)

        # Should revert when calling with oracle not set
        with boa.reverts("Oracle not configured"):
            lz_block_relay.internal._commit_block(block_data["number"], block_data["hash"])

    # Set oracle back and test normal operation
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_block_oracle(block_oracle.address)

    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]

    # Call the internal commit function
    with boa.env.prank(dev_deployer):
        lz_block_relay.internal._commit_block(test_block_number, test_block_hash)

    # Verify the block was committed to oracle
    assert (
        block_oracle.committer_votes(lz_block_relay.address, test_block_number) == test_block_hash
    )
