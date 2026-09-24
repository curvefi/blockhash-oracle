"""Test for LZBlockRelay broadcast_latest_block function."""

import pytest
import boa

from conftest import LZ_READ_CHANNEL, LZ_EID

CONTRACT_CALLER = "tests/mocks/ContractCaller.vy"


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


@pytest.mark.mainnet
def test_broadcast_block_refund_is_non_fatal(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """A caller that cannot take the change still gets its broadcast, and RefundFailed records it."""
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
    caller = boa.load(CONTRACT_CALLER, False)  # rejects ETH
    boa.env.set_balance(caller.address, fee + skipped_fee)
    data = lz_block_relay.broadcast_block.prepare_calldata(
        n, [sent_eid, unset_eid], [fee, skipped_fee], 150_000
    )

    with boa.env.prank(caller.address):
        caller.execute(lz_block_relay.address, data, value=fee + skipped_fee)

    events = caller.get_logs()
    failed = [e for e in events if type(e).__name__ == "RefundFailed"]
    assert len(failed) == 1
    assert failed[0].amount == skipped_fee
    assert [
        t.eid for t in [e for e in events if type(e).__name__ == "BlockHashBroadcast"][0].targets
    ] == [sent_eid]


@pytest.mark.mainnet
def test_broadcast_block_refuses_overpayment(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """Value above the sum of target fees is refused rather than absorbed, as on the Chainlink relay."""
    n, h = block_data["number"], block_data["hash"]
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers([30110], [boa.env.generate_address()])
        lz_block_relay.set_block_oracle(block_oracle.address)
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)
        block_oracle.add_committer(lz_block_relay.address, True)
        block_oracle.admin_apply_block(n, h)
    lz_block_relay.eval(f"self.received_blocks[{n}] = {'0x' + h.hex()}")

    fee = lz_block_relay.quote_broadcast_fees([30110], 150_000)[0]
    user = boa.env.generate_address()
    boa.env.set_balance(user, fee + 1)

    with boa.env.prank(user):
        with boa.reverts("Insufficient message value"):
            lz_block_relay.broadcast_block(n, [30110], [fee], 150_000, value=fee + 1)


_MOCK_ERC20 = """# pragma version 0.4.3
balanceOf: public(HashMap[address, uint256])

@external
def mint(_to: address, _amount: uint256):
    self.balanceOf[_to] += _amount

@external
def transfer(_to: address, _amount: uint256) -> bool:
    self.balanceOf[msg.sender] -= _amount
    self.balanceOf[_to] += _amount
    return True
"""


@pytest.mark.mainnet
def test_owner_recovers_erc20(forked_env, lz_block_relay, dev_deployer):
    """A data-only relay can still receive a direct transfer; its Chainlink twin already recovers."""
    token = boa.loads(_MOCK_ERC20)
    recipient = boa.env.generate_address()
    token.mint(lz_block_relay.address, 1000)

    with boa.env.prank(dev_deployer):
        lz_block_relay.recover_erc20(token.address, recipient, 1000)

    assert token.balanceOf(lz_block_relay.address) == 0
    assert token.balanceOf(recipient) == 1000
