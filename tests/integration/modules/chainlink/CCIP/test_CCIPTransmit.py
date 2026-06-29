"""Test CCIP module _transmit function (requires mainnet fork — calls real ccipSend)."""

import boa
import pytest
from boa.contracts.event_decoder import RawLogEntry
from conftest import BASE_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT


def _build_test_message(ccip_module, receiver):
    """Build a minimal EVM2AnyMessage for testing."""
    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))
    extra_args = ccip_module.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)
    return ccip_module.build_simple_message(receiver, data, extra_args)


@pytest.mark.mainnet
def test_transmit_deducts_fee_and_emits_ccip_event(ccip_module_mainnet, dev_deployer):
    """_transmit calls ccipSend: balance decreases by exactly the fee and the CCIP
    onramp emits CCIPMessageSent with the target chain selector in topics[1]."""
    receiver = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(BASE_CHAIN_SELECTOR, receiver)

    message = _build_test_message(ccip_module_mainnet, receiver)
    fee = ccip_module_mainnet.quote(BASE_CHAIN_SELECTOR, message)

    boa.env.set_balance(ccip_module_mainnet.address, fee)
    balance_before = boa.env.get_balance(ccip_module_mainnet.address)

    ccip_module_mainnet.transmit(BASE_CHAIN_SELECTOR, message, fee)

    # Capture logs before any getter — view calls reset boa's log buffer
    events = ccip_module_mainnet.get_logs()

    # The CCIP onramp is a forked mainnet contract unknown to boa → RawLogEntry.
    # CCIPMessageSent indexes destChainSelector as topics[1]; WETH logs carry an
    # address in topics[1] (>> uint64 range) so they cannot collide with selectors.
    sent_selectors = [
        e.topics[1] for e in events if isinstance(e, RawLogEntry) and len(e.topics) >= 2
    ]
    assert BASE_CHAIN_SELECTOR in sent_selectors

    assert boa.env.get_balance(ccip_module_mainnet.address) == balance_before - fee


@pytest.mark.mainnet
def test_transmit_insufficient_balance_reverts(ccip_module_mainnet, dev_deployer):
    """_transmit reverts when the contract balance is less than the requested fee."""
    receiver = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(BASE_CHAIN_SELECTOR, receiver)

    message = _build_test_message(ccip_module_mainnet, receiver)
    fee = ccip_module_mainnet.quote(BASE_CHAIN_SELECTOR, message)

    boa.env.set_balance(ccip_module_mainnet.address, fee - 1)

    with boa.reverts():
        ccip_module_mainnet.transmit(BASE_CHAIN_SELECTOR, message, fee)


@pytest.mark.mainnet
def test_transmit_fake_selector_reverts(ccip_module_mainnet, dev_deployer):
    """_transmit reverts when the chain selector is not recognized by the real router."""
    fake_selector = 111
    receiver = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module_mainnet.set_receiver(fake_selector, receiver)

    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))
    extra_args = ccip_module_mainnet.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)
    message = ccip_module_mainnet.build_simple_message(receiver, data, extra_args)

    boa.env.set_balance(ccip_module_mainnet.address, 10**18)

    with boa.reverts():
        ccip_module_mainnet.transmit(fake_selector, message, 10**14)
