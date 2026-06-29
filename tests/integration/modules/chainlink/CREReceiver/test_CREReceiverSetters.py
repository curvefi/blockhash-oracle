"""Test CREReceiver module setter functions."""

import boa
from conftest import EMPTY_ADDRESS, compute_workflow_name_bytes


def test_set_forwarder_address(cre_receiver, dev_deployer):
    """Owner sets forwarder address; stored and ForwarderAddressUpdated event emitted."""
    forwarder = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)

    events = cre_receiver.get_logs()
    assert cre_receiver.forwarder_address() == forwarder
    assert any("ForwarderAddressUpdated" in str(e) for e in events)


def test_set_forwarder_address_zero_emits_warning(cre_receiver, dev_deployer):
    """Setting forwarder to zero address emits SecurityWarning alongside the update event."""
    forwarder = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(EMPTY_ADDRESS)

    events = cre_receiver.get_logs()
    assert cre_receiver.forwarder_address() == EMPTY_ADDRESS
    assert any("SecurityWarning" in str(e) for e in events)
    assert any("ForwarderAddressUpdated" in str(e) for e in events)


def test_set_forwarder_address_unauthorized(cre_receiver):
    """Non-owner cannot set forwarder address."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            cre_receiver.set_forwarder_address(boa.env.generate_address())


def test_set_expected_author(cre_receiver, dev_deployer):
    """Owner sets expected author; stored, event emitted, and clearable by zero address."""
    author = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_author(author)

    events = cre_receiver.get_logs()
    assert cre_receiver.expected_author() == author
    assert any("ExpectedAuthorUpdated" in str(e) for e in events)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_author(EMPTY_ADDRESS)

    assert cre_receiver.expected_author() == EMPTY_ADDRESS


def test_set_expected_author_unauthorized(cre_receiver):
    """Non-owner cannot set expected author."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            cre_receiver.set_expected_author(boa.env.generate_address())


def test_set_expected_workflow_id(cre_receiver, dev_deployer):
    """Owner sets expected workflow ID; stored, event emitted, and clearable by zero bytes32."""
    workflow_id = bytes.fromhex("ab" * 32)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_workflow_id(workflow_id)

    events = cre_receiver.get_logs()
    assert cre_receiver.expected_workflow_id() == workflow_id
    assert any("ExpectedWorkflowIdUpdated" in str(e) for e in events)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_workflow_id(bytes(32))

    assert cre_receiver.expected_workflow_id() == bytes(32)


def test_set_expected_workflow_id_unauthorized(cre_receiver):
    """Non-owner cannot set expected workflow ID."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            cre_receiver.set_expected_workflow_id(bytes(32))


def test_set_expected_workflow_name(cre_receiver, dev_deployer):
    """Owner sets expected workflow name; stored as hashed bytes10 and event emitted."""
    name = "my_workflow"
    expected_bytes10 = compute_workflow_name_bytes(name)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_workflow_name(name)

    events = cre_receiver.get_logs()
    assert cre_receiver.expected_workflow_name() == expected_bytes10
    assert any("ExpectedWorkflowNameUpdated" in str(e) for e in events)


def test_set_expected_workflow_name_empty_clears(cre_receiver, dev_deployer):
    """Setting workflow name to empty string resets it to bytes10(0)."""
    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_workflow_name("some_name")

    assert cre_receiver.expected_workflow_name() != bytes(10)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_expected_workflow_name("")

    assert cre_receiver.expected_workflow_name() == bytes(10)


def test_set_expected_workflow_name_unauthorized(cre_receiver):
    """Non-owner cannot set expected workflow name."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            cre_receiver.set_expected_workflow_name("hack")
