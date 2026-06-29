"""Test CREReceiver module initialization and interface support."""

from conftest import EMPTY_ADDRESS


def test_initial_state(cre_receiver, dev_deployer):
    """All permission fields are unset (zero) after deployment; deployer is the owner."""
    assert cre_receiver.owner() == dev_deployer
    assert cre_receiver.forwarder_address() == EMPTY_ADDRESS
    assert cre_receiver.expected_author() == EMPTY_ADDRESS
    assert cre_receiver.expected_workflow_name() == bytes(10)
    assert cre_receiver.expected_workflow_id() == bytes(32)


def test_supports_interface(cre_receiver):
    """supportsInterface returns True for ERC165 and IReceiver; False for unknown."""
    assert cre_receiver.supportsInterface(bytes.fromhex("01ffc9a7")) is True  # ERC165
    assert cre_receiver.supportsInterface(bytes.fromhex("805f2132")) is True  # IReceiver
    assert cre_receiver.supportsInterface(bytes.fromhex("deadbeef")) is False
