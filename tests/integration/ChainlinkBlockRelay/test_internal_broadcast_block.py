"""Test for ChainlinkBlockRelay _broadcast_block internal function."""

import pytest
import boa
from conftest import BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT


@pytest.mark.mainnet
def test_broadcast_block(forked_env, chainlink_block_relay, dev_deployer, block_data):
    """A broadcast to registered peers emits BlockHashBroadcast with the right
    targets/fees and deducts the CCIP fees from the contract balance."""
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]

    test_selectors = [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR]
    test_addresses = [boa.env.generate_address(), boa.env.generate_address()]

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_peers(test_selectors, test_addresses)

    fees = chainlink_block_relay.quote_broadcast_fees(test_selectors, CCIP_RECEIVE_GAS_LIMIT)
    total_fee = sum(fees)
    assert total_fee > 0
    broadcast_targets = [(test_selectors[i], fees[i]) for i in range(2)]

    initial_balance = 10**20
    boa.env.set_balance(chainlink_block_relay.address, initial_balance)

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.internal._broadcast_block(
            test_block_number,
            test_block_hash,
            (broadcast_targets, CCIP_RECEIVE_GAS_LIMIT, dev_deployer),
        )

    events = chainlink_block_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    evt = broadcast_events[0]
    assert evt.block_number == test_block_number
    assert evt.block_hash == test_block_hash
    assert [t.chain_selector for t in evt.targets] == test_selectors
    assert [t.fee for t in evt.targets] == list(fees)

    # fees deducted from contract balance
    assert boa.env.get_balance(chainlink_block_relay.address) == initial_balance - total_fee


@pytest.mark.mainnet
def test_broadcast_block_skips_unregistered_peers(
    forked_env, chainlink_block_relay, dev_deployer, block_data
):
    """Test that chains without a registered peer are skipped and excluded from the event."""
    unregistered_selector = 999
    test_address = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_peer(BASE_CHAIN_SELECTOR, test_address)

    fees = chainlink_block_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)
    boa.env.set_balance(chainlink_block_relay.address, 10**20)

    broadcast_targets = [
        (BASE_CHAIN_SELECTOR, fees[0]),
        (unregistered_selector, 0),
    ]

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.internal._broadcast_block(
            block_data["number"],
            block_data["hash"],
            (broadcast_targets, CCIP_RECEIVE_GAS_LIMIT, dev_deployer),
        )

    events = chainlink_block_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    # Only the registered chain appears in the event (fix for review finding #2)
    assert len(broadcast_events[0].targets) == 1
    assert broadcast_events[0].targets[0].chain_selector == BASE_CHAIN_SELECTOR


@pytest.mark.mainnet
def test_broadcast_block_all_peers_unregistered(
    forked_env, chainlink_block_relay, dev_deployer, block_data
):
    """Test broadcast with all targets unregistered still emits event with empty targets list."""
    broadcast_targets = [(111, 0), (222, 0)]  # fake selectors, no peers registered, no router call

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.internal._broadcast_block(
            block_data["number"],
            block_data["hash"],
            (broadcast_targets, CCIP_RECEIVE_GAS_LIMIT, dev_deployer),
        )

    events = chainlink_block_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    assert len(broadcast_events[0].targets) == 0
