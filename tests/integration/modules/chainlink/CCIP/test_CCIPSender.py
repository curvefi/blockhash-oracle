"""Test CCIP module outbound path: quote fee via real mainnet router (requires fork)."""

import pytest
from conftest import BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT
import boa


@pytest.mark.mainnet
def test_quote_fee_registered_peer(ccip_module_mainnet, dev_deployer):
    """quote returns a positive fee from the real router when a peer is registered."""
    receiver = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(BASE_CHAIN_SELECTOR, receiver)

    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))
    extra_args = ccip_module_mainnet.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)
    message = ccip_module_mainnet.build_simple_message(receiver, data, extra_args)

    fee = ccip_module_mainnet.quote(BASE_CHAIN_SELECTOR, message)
    assert fee > 0


@pytest.mark.mainnet
def test_quote_fee_two_chains(ccip_module_mainnet, dev_deployer):
    """quote returns independent positive fees for two distinct real chains."""
    receiver_base = boa.env.generate_address()
    receiver_arb = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(BASE_CHAIN_SELECTOR, receiver_base)
        ccip_module_mainnet.set_receiver(ARBITRUM_CHAIN_SELECTOR, receiver_arb)

    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))
    extra_args = ccip_module_mainnet.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)

    msg_base = ccip_module_mainnet.build_simple_message(receiver_base, data, extra_args)
    msg_arb = ccip_module_mainnet.build_simple_message(receiver_arb, data, extra_args)

    fee_base = ccip_module_mainnet.quote(BASE_CHAIN_SELECTOR, msg_base)
    fee_arb = ccip_module_mainnet.quote(ARBITRUM_CHAIN_SELECTOR, msg_arb)

    assert fee_base > 0
    assert fee_arb > 0


@pytest.mark.mainnet
def test_quote_fee_unsupported_chain_returns_zero(ccip_module_mainnet, dev_deployer):
    """quote returns 0 (instead of reverting) when a peer is registered for a chain
    selector the real router does not recognize."""
    fake_selector = 111
    receiver = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(fake_selector, receiver)

    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))
    extra_args = ccip_module_mainnet.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)
    message = ccip_module_mainnet.build_simple_message(receiver, data, extra_args)

    fee = ccip_module_mainnet.quote(fake_selector, message)
    assert fee == 0


@pytest.mark.mainnet
def test_quote_fee_higher_gas_costs_more(ccip_module_mainnet, dev_deployer):
    """A higher ccipReceive gas limit yields an equal or higher fee from the router."""
    receiver = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(BASE_CHAIN_SELECTOR, receiver)

    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))

    extra_low = ccip_module_mainnet.build_extra_args(50_000)
    extra_high = ccip_module_mainnet.build_extra_args(500_000)

    msg_low = ccip_module_mainnet.build_simple_message(receiver, data, extra_low)
    msg_high = ccip_module_mainnet.build_simple_message(receiver, data, extra_high)

    fee_low = ccip_module_mainnet.quote(BASE_CHAIN_SELECTOR, msg_low)
    fee_high = ccip_module_mainnet.quote(BASE_CHAIN_SELECTOR, msg_high)

    assert fee_low > 0
    assert fee_high >= fee_low
