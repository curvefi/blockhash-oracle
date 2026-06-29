"""Test CREReceiver module _on_report validation: forwarder check and all permission paths."""

import boa
from conftest import encode_metadata, compute_workflow_name_bytes


def test_on_report_no_forwarder_configured(cre_receiver):
    """onReport reverts from any caller when no forwarder has ever been set (address is zero)."""
    caller = boa.env.generate_address()
    with boa.env.prank(caller):
        with boa.reverts("Invalid sender"):
            cre_receiver.onReport(encode_metadata(), b"")


def test_on_report_rejects_non_forwarder(cre_receiver, dev_deployer):
    """onReport reverts for any caller that is not the configured forwarder."""
    forwarder = boa.env.generate_address()
    stranger = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)

    with boa.env.prank(stranger):
        with boa.reverts("Invalid sender"):
            cre_receiver.onReport(encode_metadata(), b"")


def test_on_report_accepts_valid_forwarder(cre_receiver, dev_deployer):
    """onReport with no permission checks passes when caller is the forwarder."""
    forwarder = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)

    with boa.env.prank(forwarder):
        cre_receiver.onReport(encode_metadata(), b"")  # must not revert


def test_on_report_workflow_id_mismatch(cre_receiver, dev_deployer):
    """onReport reverts when expected_workflow_id is set and the message carries a different ID."""
    forwarder = boa.env.generate_address()
    expected_id = bytes.fromhex("aa" * 32)
    wrong_id = bytes.fromhex("bb" * 32)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_workflow_id(expected_id)

    with boa.env.prank(forwarder):
        with boa.reverts("Invalid workflow id"):
            cre_receiver.onReport(encode_metadata(workflow_id=wrong_id), b"")


def test_on_report_workflow_id_matches(cre_receiver, dev_deployer):
    """onReport passes when expected_workflow_id matches the message."""
    forwarder = boa.env.generate_address()
    expected_id = bytes.fromhex("aa" * 32)

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_workflow_id(expected_id)

    with boa.env.prank(forwarder):
        cre_receiver.onReport(encode_metadata(workflow_id=expected_id), b"")  # must not revert


def test_on_report_author_mismatch(cre_receiver, dev_deployer):
    """onReport reverts when expected_author is set and the message owner differs."""
    forwarder = boa.env.generate_address()
    expected_author = boa.env.generate_address()
    wrong_author = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_author(expected_author)

    with boa.env.prank(forwarder):
        with boa.reverts("Invalid author"):
            cre_receiver.onReport(encode_metadata(workflow_owner=wrong_author), b"")


def test_on_report_author_matches(cre_receiver, dev_deployer):
    """onReport passes when expected_author matches the message owner."""
    forwarder = boa.env.generate_address()
    expected_author = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_author(expected_author)

    with boa.env.prank(forwarder):
        cre_receiver.onReport(
            encode_metadata(workflow_owner=expected_author), b""
        )  # must not revert


def test_on_report_workflow_name_requires_author(cre_receiver, dev_deployer):
    """onReport reverts when expected_workflow_name is set but expected_author is not."""
    forwarder = boa.env.generate_address()
    name = "my_workflow"

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_workflow_name(name)
        # intentionally NOT calling set_expected_author

    name_bytes10 = compute_workflow_name_bytes(name)
    metadata = encode_metadata(workflow_name=name_bytes10)

    with boa.env.prank(forwarder):
        with boa.reverts("Workflow name requires author validation"):
            cre_receiver.onReport(metadata, b"")


def test_on_report_workflow_name_mismatch(cre_receiver, dev_deployer):
    """onReport reverts when expected_workflow_name is set and the name doesn't match."""
    forwarder = boa.env.generate_address()
    author = boa.env.generate_address()
    name = "correct_name"

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_author(author)
        cre_receiver.set_expected_workflow_name(name)

    wrong_name_bytes = b"\xff" * 10
    metadata = encode_metadata(workflow_name=wrong_name_bytes, workflow_owner=author)

    with boa.env.prank(forwarder):
        with boa.reverts("Invalid workflow name"):
            cre_receiver.onReport(metadata, b"")


def test_on_report_all_checks_pass(cre_receiver, dev_deployer):
    """All permission checks pass together: forwarder, workflow_id, author, and name."""
    forwarder = boa.env.generate_address()
    author = boa.env.generate_address()
    workflow_id = bytes.fromhex("cc" * 32)
    name = "verified_workflow"

    with boa.env.prank(dev_deployer):
        cre_receiver.set_forwarder_address(forwarder)
        cre_receiver.set_expected_author(author)
        cre_receiver.set_expected_workflow_id(workflow_id)
        cre_receiver.set_expected_workflow_name(name)

    name_bytes10 = compute_workflow_name_bytes(name)
    metadata = encode_metadata(
        workflow_id=workflow_id,
        workflow_name=name_bytes10,
        workflow_owner=author,
    )

    with boa.env.prank(forwarder):
        cre_receiver.onReport(metadata, b"")  # must not revert
