"""Test for ChainlinkBlockRelay broadcast_latest_block function."""

import pytest
import boa
from boa.contracts.event_decoder import RawLogEntry
from conftest import BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT


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
        with boa.reverts("No confirmed blocks"):
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
        configured_relay.set_peer(BASE_CHAIN_SELECTOR, test_address)

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
