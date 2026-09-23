"""Test for ChainlinkBlockRelay broadcast_latest_block function."""

import pytest
import boa
from boa.contracts.event_decoder import RawLogEntry
from conftest import BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT

CONTRACT_CALLER = "tests/mocks/ContractCaller.vy"


def _seed_confirmed_block(relay, block_oracle, dev_deployer, block_number, block_hash):
    """Simulate a block arriving via onReport: set received_blocks and confirm in oracle."""
    with boa.env.prank(dev_deployer):
        relay.eval(f"self.received_blocks[{block_number}] = 0x{bytes(block_hash).hex()}")
        block_oracle.admin_apply_block(block_number, block_hash)


def _ccip_message_sent_selectors(events):
    """destChainSelectors of the CCIPMessageSent events emitted by the live CCIP onramp.

    The onramp is a forked mainnet contract unknown to boa, so its logs come back as
    raw entries. CCIPMessageSent indexes destChainSelector as its first indexed arg
    (topics[1]) — matching on that alone is robust to a CCIP onramp upgrade. The WETH
    Deposit/Transfer logs the router also emits carry the router *address* in topics[1]
    (>> uint64 range), so they can never collide with a chain selector.
    """
    return [e.topics[1] for e in events if isinstance(e, RawLogEntry) and len(e.topics) >= 2]


@pytest.mark.mainnet
def test_broadcast_latest_block(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Test broadcasting the latest confirmed block to multiple chains."""
    test_selectors = [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR]
    test_addresses = [boa.env.generate_address(), boa.env.generate_address()]

    with boa.env.prank(dev_deployer):
        configured_relay.set_peers(test_selectors, test_addresses)

    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_data["number"], block_data["hash"]
    )

    fees = configured_relay.quote_broadcast_fees(test_selectors, CCIP_RECEIVE_GAS_LIMIT)
    total_value = sum(fees)

    user = boa.env.generate_address()
    boa.env.set_balance(user, total_value)

    relay_balance_before = boa.env.get_balance(configured_relay.address)

    with boa.env.prank(user):
        configured_relay.broadcast_latest_block(
            test_selectors, fees, CCIP_RECEIVE_GAS_LIMIT, value=total_value
        )

    events = configured_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    assert broadcast_events[0].block_number == block_data["number"]
    assert broadcast_events[0].block_hash == block_data["hash"]

    # The CCIP onramp must have emitted a CCIPMessageSent for each target chain
    sent = _ccip_message_sent_selectors(events)
    assert BASE_CHAIN_SELECTOR in sent
    assert ARBITRUM_CHAIN_SELECTOR in sent

    # The relay forwarded exactly the requested fees out to the router: msg.value
    # flows in, sum(fees) flows out via ccipSend, leaving the prior balance.
    assert boa.env.get_balance(configured_relay.address) == relay_balance_before


@pytest.mark.mainnet
def test_broadcast_latest_block_oracle_not_configured(forked_env, chainlink_block_relay):
    """Test that broadcasting fails when the block oracle is not set."""
    user = boa.env.generate_address()
    with boa.env.prank(user):
        with boa.reverts("Oracle not configured"):
            chainlink_block_relay.broadcast_latest_block([], [], CCIP_RECEIVE_GAS_LIMIT)


@pytest.mark.mainnet
def test_broadcast_latest_block_length_mismatch(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Test that mismatched selector/fee arrays revert before any router call."""
    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_data["number"], block_data["hash"]
    )

    user = boa.env.generate_address()
    boa.env.set_balance(user, 10**20)

    with boa.env.prank(user):
        with boa.reverts("Length mismatch"):
            configured_relay.broadcast_latest_block([111, 222], [10**14], CCIP_RECEIVE_GAS_LIMIT)


@pytest.mark.mainnet
def test_broadcast_latest_block_no_confirmed_blocks(forked_env, configured_relay):
    """Test that broadcasting fails when no blocks are confirmed in the oracle."""
    user = boa.env.generate_address()
    boa.env.set_balance(user, 10**20)

    with boa.env.prank(user):
        with boa.reverts("Block not confirmed"):
            configured_relay.broadcast_latest_block([], [], CCIP_RECEIVE_GAS_LIMIT)


@pytest.mark.mainnet
def test_broadcast_latest_block_unknown_source(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Test that broadcasting fails when the block was not received via onReport."""
    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(block_data["number"], block_data["hash"])

    user = boa.env.generate_address()
    boa.env.set_balance(user, 10**20)

    with boa.env.prank(user):
        with boa.reverts("Unknown source"):
            configured_relay.broadcast_latest_block([], [], CCIP_RECEIVE_GAS_LIMIT)


@pytest.mark.mainnet
def test_broadcast_latest_block_insufficient_value(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Test that broadcasting fails when msg.value is less than the sum of fees."""
    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_data["number"], block_data["hash"]
    )

    user = boa.env.generate_address()
    boa.env.set_balance(user, 10**20)

    # fee > 0 but value = 0 → "Insufficient message value" before router is touched
    with boa.env.prank(user):
        with boa.reverts("Insufficient message value"):
            configured_relay.broadcast_latest_block(
                [111], [10**14], CCIP_RECEIVE_GAS_LIMIT, value=0
            )


@pytest.mark.mainnet
def test_broadcast_latest_block_refunds_excess_max_fee(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """max_fee above the live fee: relay sends the live fee and refunds the rest to the caller."""
    test_address = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_receiver(BASE_CHAIN_SELECTOR, test_address)

    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_data["number"], block_data["hash"]
    )

    live_fee = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)[
        0
    ]
    pad = 10**15
    max_fee = live_fee + pad

    user = boa.env.generate_address()
    boa.env.set_balance(user, max_fee)
    relay_balance_before = boa.env.get_balance(configured_relay.address)

    with boa.env.prank(user):
        configured_relay.broadcast_latest_block(
            [BASE_CHAIN_SELECTOR], [max_fee], CCIP_RECEIVE_GAS_LIMIT, value=max_fee
        )

    # caller refunded the unused portion; relay only spent the live fee (net balance unchanged)
    assert boa.env.get_balance(user) == pad
    assert boa.env.get_balance(configured_relay.address) == relay_balance_before


@pytest.mark.mainnet
def test_broadcast_latest_block_reverts_when_max_fee_below_live(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A max_fee below the live CCIP fee reverts (never overpays). The public path stays strict;
    only the CRE path skips a destination, to protect the commit."""
    test_address = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_receiver(BASE_CHAIN_SELECTOR, test_address)

    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_data["number"], block_data["hash"]
    )

    live_fee = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)[
        0
    ]

    # value must equal sum(max_fee); set both to live_fee - 1 so the payment check
    # passes and _transmit is what reverts (live fee exceeds the max_fee ceiling).
    user = boa.env.generate_address()
    boa.env.set_balance(user, live_fee)

    with boa.env.prank(user):
        with boa.reverts("Transmit failed"):
            configured_relay.broadcast_latest_block(
                [BASE_CHAIN_SELECTOR], [live_fee - 1], CCIP_RECEIVE_GAS_LIMIT, value=live_fee - 1
            )


@pytest.mark.mainnet
def test_broadcast_latest_block_only_confirmed_block_is_broadcast(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Test that only the latest confirmed block is broadcast (not a stale one)."""
    # Stale, lower-numbered block with a synthetic hash
    block_number_a = block_data["number"] - 100
    block_hash_a = bytes.fromhex("aaaa0000" * 8)
    # Latest confirmed block uses the real fetched block data
    block_number_b = block_data["number"]
    block_hash_b = block_data["hash"]

    test_address = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_receiver(BASE_CHAIN_SELECTOR, test_address)

    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_number_a, block_hash_a
    )
    _seed_confirmed_block(
        configured_relay, block_oracle, dev_deployer, block_number_b, block_hash_b
    )

    fees = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)

    user = boa.env.generate_address()
    boa.env.set_balance(user, fees[0])

    relay_balance_before = boa.env.get_balance(configured_relay.address)

    with boa.env.prank(user):
        configured_relay.broadcast_latest_block(
            [BASE_CHAIN_SELECTOR], fees, CCIP_RECEIVE_GAS_LIMIT, value=fees[0]
        )

    events = configured_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    assert broadcast_events[0].block_number == block_number_b
    assert broadcast_events[0].block_hash == block_hash_b

    # The CCIP onramp must have emitted a CCIPMessageSent for the target chain
    assert BASE_CHAIN_SELECTOR in _ccip_message_sent_selectors(events)

    # The relay forwarded exactly the requested fee out to the router.
    assert boa.env.get_balance(configured_relay.address) == relay_balance_before


# ─── broadcast_block: any received block, not only the oracle's latest ──────


@pytest.mark.mainnet
def test_broadcast_block_after_another_source_confirms_newer(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Another source confirming a newer block strands broadcast_latest_block on "Unknown source",
    but broadcast_block still serves the block this relay received."""
    n, h = block_data["number"], block_data["hash"]
    with boa.env.prank(dev_deployer):
        configured_relay.set_receiver(BASE_CHAIN_SELECTOR, boa.env.generate_address())
    _seed_confirmed_block(configured_relay, block_oracle, dev_deployer, n, h)

    # a newer block confirmed without passing through this relay
    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(n + 10, bytes.fromhex("bb" * 32))

    fees = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)
    user = boa.env.generate_address()
    boa.env.set_balance(user, 2 * sum(fees))

    with boa.env.prank(user):
        with boa.reverts("Unknown source"):
            configured_relay.broadcast_latest_block(
                [BASE_CHAIN_SELECTOR], fees, CCIP_RECEIVE_GAS_LIMIT, value=sum(fees)
            )
        configured_relay.broadcast_block(
            n, [BASE_CHAIN_SELECTOR], fees, CCIP_RECEIVE_GAS_LIMIT, value=sum(fees)
        )

    broadcast = [e for e in configured_relay.get_logs() if type(e).__name__ == "BlockHashBroadcast"]
    assert len(broadcast) == 1
    assert broadcast[0].block_number == n
    assert broadcast[0].block_hash == h


@pytest.mark.mainnet
def test_broadcast_block_refuses_unconfirmed(forked_env, configured_relay, block_data):
    """A block this relay received but the oracle has not confirmed is not broadcast."""
    n, h = block_data["number"], block_data["hash"]
    configured_relay.eval(f"self.received_blocks[{n}] = 0x{bytes(h).hex()}")

    with boa.reverts("Block not confirmed"):
        configured_relay.broadcast_block(n, [], [], CCIP_RECEIVE_GAS_LIMIT)


@pytest.mark.mainnet
def test_broadcast_block_refuses_block_it_never_received(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A confirmed block that reached the oracle through another source is not broadcast."""
    n, h = block_data["number"], block_data["hash"]
    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(n, h)

    with boa.reverts("Unknown source"):
        configured_relay.broadcast_block(n, [], [], CCIP_RECEIVE_GAS_LIMIT)


@pytest.mark.mainnet
def test_broadcast_refunds_fee_of_unconfigured_destination(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A destination without a receiver is skipped and its fee comes back with the change,
    instead of staying in the relay for the owner."""
    n, h = block_data["number"], block_data["hash"]
    unconfigured = 999
    with boa.env.prank(dev_deployer):
        configured_relay.set_receiver(BASE_CHAIN_SELECTOR, boa.env.generate_address())
    _seed_confirmed_block(configured_relay, block_oracle, dev_deployer, n, h)

    quote = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)[0]
    skipped_fee = 10**15
    user = boa.env.generate_address()
    boa.env.set_balance(user, quote + skipped_fee)
    relay_before = boa.env.get_balance(configured_relay.address)

    with boa.env.prank(user):
        configured_relay.broadcast_block(
            n,
            [BASE_CHAIN_SELECTOR, unconfigured],
            [quote, skipped_fee],
            CCIP_RECEIVE_GAS_LIMIT,
            value=quote + skipped_fee,
        )

    assert boa.env.get_balance(user) == skipped_fee  # paid only for the destination it reached
    assert boa.env.get_balance(configured_relay.address) == relay_before


# ─── Contract callers ────────────────────────────────────────────────────────


def _contract_broadcast(relay, block_oracle, dev_deployer, block_data, accept_eth, headroom):
    """A contract broadcasts a received block with fee caps `headroom` times the quote."""
    n, h = block_data["number"], block_data["hash"]
    with boa.env.prank(dev_deployer):
        relay.set_receiver(BASE_CHAIN_SELECTOR, boa.env.generate_address())
    _seed_confirmed_block(relay, block_oracle, dev_deployer, n, h)

    quote = relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)[0]
    caps = [quote * headroom]
    caller = boa.load(CONTRACT_CALLER, accept_eth)
    boa.env.set_balance(caller.address, sum(caps))
    data = relay.broadcast_block.prepare_calldata(
        n, [BASE_CHAIN_SELECTOR], caps, CCIP_RECEIVE_GAS_LIMIT
    )
    with boa.env.prank(caller.address):  # funds the call from the caller's own balance
        caller.execute(relay.address, data, value=sum(caps))
    return caller, quote


@pytest.mark.mainnet
def test_contract_caller_exact_fees_broadcasts(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Exact fees leave no refund, so none is attempted: send used to call the caller with zero gas
    and revert the whole broadcast."""
    caller, _ = _contract_broadcast(
        configured_relay, block_oracle, dev_deployer, block_data, accept_eth=True, headroom=1
    )

    events = caller.get_logs()  # the transaction went through the caller
    assert len([e for e in events if type(e).__name__ == "BlockHashBroadcast"]) == 1
    assert not [e for e in events if type(e).__name__ == "RefundFailed"]
    assert caller.received() == 0


@pytest.mark.mainnet
def test_contract_caller_receives_refund_over_stipend(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A caller whose receive needs more than send's stipend still gets its unused fee back."""
    caller, quote = _contract_broadcast(
        configured_relay, block_oracle, dev_deployer, block_data, accept_eth=True, headroom=2
    )

    assert caller.received() == quote  # cap 2x quote, the router took 1x


@pytest.mark.mainnet
def test_contract_caller_rejecting_eth_still_broadcasts(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A caller that cannot take the change still gets its broadcast; the refund stays in the
    treasury and RefundFailed records it."""
    balance_before = boa.env.get_balance(configured_relay.address)
    caller, quote = _contract_broadcast(
        configured_relay, block_oracle, dev_deployer, block_data, accept_eth=False, headroom=2
    )

    events = caller.get_logs()  # the transaction went through the caller
    assert len([e for e in events if type(e).__name__ == "BlockHashBroadcast"]) == 1
    failed = [e for e in events if type(e).__name__ == "RefundFailed"]
    assert len(failed) == 1
    assert failed[0].requester == caller.address
    assert failed[0].amount == quote
    assert boa.env.get_balance(configured_relay.address) == balance_before + quote
