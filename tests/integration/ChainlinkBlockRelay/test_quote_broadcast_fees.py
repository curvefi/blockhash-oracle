"""Test for ChainlinkBlockRelay quote_broadcast_fees function."""

import pytest
import boa
from conftest import BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT


@pytest.mark.mainnet
def test_quote_broadcast_fees_with_peers(forked_env, chainlink_block_relay, dev_deployer):
    """Test that quoting fees for registered chains returns a positive fee from the real router."""
    test_selectors = [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR]
    test_addresses = [boa.env.generate_address() for _ in range(2)]

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_peers(test_selectors, test_addresses)

    fees = chainlink_block_relay.quote_broadcast_fees(test_selectors, CCIP_RECEIVE_GAS_LIMIT)

    assert len(fees) == len(test_selectors)
    for fee in fees:
        assert fee > 0


@pytest.mark.mainnet
def test_quote_broadcast_fees_without_peers(forked_env, chainlink_block_relay):
    """Test that fee is 0 for chains without a registered peer (router is not queried)."""
    no_peer_selectors = [999, 1000]
    fees = chainlink_block_relay.quote_broadcast_fees(no_peer_selectors, CCIP_RECEIVE_GAS_LIMIT)

    assert len(fees) == len(no_peer_selectors)
    for fee in fees:
        assert fee == 0


@pytest.mark.mainnet
def test_quote_broadcast_fees_mixed(forked_env, chainlink_block_relay, dev_deployer):
    """Test mixed array: registered chain returns real fee, unregistered returns 0."""
    unregistered_selector = 999
    test_address = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_receiver(BASE_CHAIN_SELECTOR, test_address)

    fees = chainlink_block_relay.quote_broadcast_fees(
        [BASE_CHAIN_SELECTOR, unregistered_selector], CCIP_RECEIVE_GAS_LIMIT
    )

    assert len(fees) == 2
    assert fees[0] > 0  # real router fee for Base
    assert fees[1] == 0  # no peer registered


@pytest.mark.mainnet
def test_quote_broadcast_fees_unsupported_chain_with_peer(
    forked_env, chainlink_block_relay, dev_deployer
):
    """Test that fee is 0 (not a revert) for a chain with a registered peer that the
    real CCIP router does not recognize."""
    fake_selector = 111
    test_address = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_receiver(fake_selector, test_address)

    fees = chainlink_block_relay.quote_broadcast_fees([fake_selector], CCIP_RECEIVE_GAS_LIMIT)

    assert fees == [0]


@pytest.mark.mainnet
def test_quote_broadcast_fees_empty_list(forked_env, chainlink_block_relay):
    """Test quoting fees for an empty selector list returns an empty array."""
    fees = chainlink_block_relay.quote_broadcast_fees([], CCIP_RECEIVE_GAS_LIMIT)
    assert fees == []


@pytest.mark.mainnet
def test_quote_broadcast_fees_gas_limit_affects_fee(
    forked_env, chainlink_block_relay, dev_deployer
):
    """Test that gas limit is forwarded to the router — higher gas limit yields higher or equal fee."""
    test_address = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_receiver(BASE_CHAIN_SELECTOR, test_address)

    fees_low_gas = chainlink_block_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], 50_000)
    fees_high_gas = chainlink_block_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], 500_000)

    assert fees_low_gas[0] > 0
    assert fees_high_gas[0] >= fees_low_gas[0]
