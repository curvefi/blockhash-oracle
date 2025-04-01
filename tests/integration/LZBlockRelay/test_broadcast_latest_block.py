"""Test for LZBlockRelay broadcast_latest_block function."""

import pytest
import boa

from conftest import LZ_READ_CHANNEL, LZ_EID


@pytest.mark.mainnet
def test_broadcast_latest_block(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """Test broadcasting the latest confirmed block."""
    # Generate a user address
    user = boa.env.generate_address()
    boa.env.set_balance(user, 10**20)  # 100 ETH

    # Setup peers for testing
    test_eids = [30110, 30111]
    test_addresses = [boa.env.generate_address(), boa.env.generate_address()]

    with boa.env.prank(dev_deployer):
        # Setup relay and oracle
        lz_block_relay.set_peers(test_eids, test_addresses)
        lz_block_relay.set_block_oracle(block_oracle.address)
        # Set a committer for block oracle
        block_oracle.add_committer(lz_block_relay.address, True)

    # Get broadcast fees
    broadcast_fees = lz_block_relay.quote_broadcast_fees(test_eids)

    # Should fail if read not enabled
    with boa.env.prank(user):
        with boa.reverts("Can only broadcast from read-enabled chains"):
            lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees)

    # Enable read functionality
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

    # Should fail with mismatched array lengths
    with boa.env.prank(user):
        with boa.reverts("Length mismatch"):
            lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees[:1])

    # Should fail if no confirmed block
    with boa.env.prank(user):
        with boa.reverts("No confirmed blocks"):
            lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees)

    # Commit and confirm a block in the oracle to test broadcasting
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]

    # # Store as a received block in the relay (to simulate it was received via lzRead)
    with boa.env.prank(dev_deployer):
        # Simulate a received block
        lz_block_relay.eval(
            f"self.received_blocks[{test_block_number}] = {'0x'+test_block_hash.hex()}"
        )
        # Need to simulate confirmation by admin (for testing)
        block_oracle.admin_apply_block(test_block_number, test_block_hash)

    # Now the broadcast should work
    total_value = sum(broadcast_fees)
    with boa.env.prank(user):
        lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees, value=total_value)

    # Verify event was emitted
    events = lz_block_relay.get_logs()
    assert any(
        "BlockHashBroadcast" in str(event) for event in events
    ), "BlockHashBroadcast event not emitted"
