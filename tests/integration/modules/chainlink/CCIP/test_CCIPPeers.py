"""Test CCIP module peer management: set_receiver, set_sender, set_peer."""

import boa
from conftest import EMPTY_ADDRESS


def test_set_receiver(ccip_module, dev_deployer):
    """Owner sets a receiver for a selector; stored and SetReceiver event emitted."""
    selector = 111
    receiver = boa.env.generate_address()

    assert ccip_module.selector_to_receiver(selector) == EMPTY_ADDRESS

    with boa.env.prank(dev_deployer):
        ccip_module.set_receiver(selector, receiver)

    events = ccip_module.get_logs()
    assert ccip_module.selector_to_receiver(selector) == receiver
    assert any("SetReceiver" in str(e) for e in events)


def test_set_sender(ccip_module, dev_deployer):
    """Owner sets a sender for a selector; stored and SetSender event emitted."""
    selector = 222
    sender = boa.env.generate_address()

    assert ccip_module.selector_to_sender(selector) == EMPTY_ADDRESS

    with boa.env.prank(dev_deployer):
        ccip_module.set_sender(selector, sender)

    events = ccip_module.get_logs()
    assert ccip_module.selector_to_sender(selector) == sender
    assert any("SetSender" in str(e) for e in events)


def test_set_peer(ccip_module, dev_deployer):
    """set_peer registers the same address as both sender and receiver; can be overwritten."""
    selector = 333
    peer = boa.env.generate_address()

    assert ccip_module.selector_to_receiver(selector) == EMPTY_ADDRESS
    assert ccip_module.selector_to_sender(selector) == EMPTY_ADDRESS

    with boa.env.prank(dev_deployer):
        ccip_module.set_peer(selector, peer)

    assert ccip_module.selector_to_receiver(selector) == peer
    assert ccip_module.selector_to_sender(selector) == peer

    new_peer = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        ccip_module.set_peer(selector, new_peer)

    assert ccip_module.selector_to_receiver(selector) == new_peer
    assert ccip_module.selector_to_sender(selector) == new_peer


def test_set_peer_unauthorized(ccip_module):
    """Non-owner cannot call set_peer."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            ccip_module.set_peer(111, boa.env.generate_address())


def test_set_receiver_unauthorized(ccip_module):
    """Non-owner cannot call set_receiver."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            ccip_module.set_receiver(111, boa.env.generate_address())


def test_set_sender_unauthorized(ccip_module):
    """Non-owner cannot call set_sender."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            ccip_module.set_sender(111, boa.env.generate_address())
