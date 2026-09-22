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
    broadcast_fees = lz_block_relay.quote_broadcast_fees(test_eids, 150_000)

    # Should fail if read not enabled
    with boa.env.prank(user):
        with boa.reverts("Can only broadcast from read-enabled chains"):
            lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees, 150_000)

    # Enable read functionality
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

    # Should fail with mismatched array lengths
    with boa.env.prank(user):
        with boa.reverts("Length mismatch"):
            lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees[:1], 150_000)

    # Should fail if no confirmed block
    with boa.env.prank(user):
        with boa.reverts("Block not confirmed"):
            lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees, 150_000)

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
        lz_block_relay.broadcast_latest_block(test_eids, broadcast_fees, 150_000, value=total_value)

    # Verify event was emitted
    events = lz_block_relay.get_logs()
    assert any(
        "BlockHashBroadcast" in str(event) for event in events
    ), "BlockHashBroadcast event not emitted"


@pytest.mark.mainnet
def test_broadcast_block_after_another_source_confirms_newer(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """Another source confirming a newer block strands broadcast_latest_block on "Unknown source",
    but broadcast_block still serves the block this relay read; blocks it did not read, or that
    are not confirmed, are refused."""
    test_eids = [30110]
    n, h = block_data["number"], block_data["hash"]

    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers(test_eids, [boa.env.generate_address()])
        lz_block_relay.set_block_oracle(block_oracle.address)
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
        block_oracle.add_committer(lz_block_relay.address, True)

    # read but not yet confirmed
    lz_block_relay.eval(f"self.received_blocks[{n}] = {'0x' + h.hex()}")
    with boa.reverts("Block not confirmed"):
        lz_block_relay.broadcast_block(n, [], [], 150_000)

    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(n, h)
        # a newer block confirmed without passing through this relay
        block_oracle.admin_apply_block(n + 10, bytes.fromhex("bb" * 32))

    with boa.reverts("Unknown source"):
        lz_block_relay.broadcast_block(n + 10, [], [], 150_000)

    fees = lz_block_relay.quote_broadcast_fees(test_eids, 150_000)
    user = boa.env.generate_address()
    boa.env.set_balance(user, 2 * sum(fees))

    with boa.env.prank(user):
        with boa.reverts("Unknown source"):
            lz_block_relay.broadcast_latest_block(test_eids, fees, 150_000, value=sum(fees))
        lz_block_relay.broadcast_block(n, test_eids, fees, 150_000, value=sum(fees))

    broadcast = [e for e in lz_block_relay.get_logs() if type(e).__name__ == "BlockHashBroadcast"]
    assert len(broadcast) == 1
    assert broadcast[0].block_number == n
    assert broadcast[0].block_hash == h


@pytest.mark.mainnet
def test_broadcast_refunds_and_logs_only_what_it_sent(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """A destination with no peer is skipped: its fee comes back to the caller and the event lists
    only the targets actually sent to."""
    sent_eid, unset_eid = 30110, 30111
    n, h = block_data["number"], block_data["hash"]
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers([sent_eid], [boa.env.generate_address()])
        lz_block_relay.set_block_oracle(block_oracle.address)
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
        block_oracle.add_committer(lz_block_relay.address, True)
        block_oracle.admin_apply_block(n, h)
    lz_block_relay.eval(f"self.received_blocks[{n}] = {'0x' + h.hex()}")

    fee = lz_block_relay.quote_broadcast_fees([sent_eid], 150_000)[0]
    skipped_fee = 10**16
    user = boa.env.generate_address()
    boa.env.set_balance(user, fee + skipped_fee)
    relay_before = boa.env.get_balance(lz_block_relay.address)

    with boa.env.prank(user):
        lz_block_relay.broadcast_block(
            n, [sent_eid, unset_eid], [fee, skipped_fee], 150_000, value=fee + skipped_fee
        )

    broadcast = [e for e in lz_block_relay.get_logs() if type(e).__name__ == "BlockHashBroadcast"]
    assert [t.eid for t in broadcast[0].targets] == [sent_eid]
    assert boa.env.get_balance(lz_block_relay.address) == relay_before
    assert boa.env.get_balance(user) >= skipped_fee  # the skipped destination's fee came back
