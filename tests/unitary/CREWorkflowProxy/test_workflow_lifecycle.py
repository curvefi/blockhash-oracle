"""What the proxy forwards to the registry, and what it refuses to forward."""

import boa

from conftest import (
    BINARY_URL,
    CONFIG,
    CONFIG_URL,
    DON_FAMILY,
    EMPTY_BYTES32,
    NEW_CONFIG,
    NEW_CONFIG_URL,
    ROGUE_BINARY_URL,
    ROGUE_WASM,
    STATUS_ACTIVE,
    TAG,
    WASM,
    WORKFLOW_NAME,
    approved_id,
    workflow_id,
)

STATUS_PAUSED = 1


def _new_config_id(proxy):
    return workflow_id(proxy.address, WORKFLOW_NAME, WASM, NEW_CONFIG)


def test_approve_binary_registers_it(proxy, registry, ownership_admin):
    wf_id = approved_id(proxy)

    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, wf_id, BINARY_URL, CONFIG_URL, b"", False)

    assert registry.upsert_count() == 1
    assert registry.last_caller() == proxy.address
    assert registry.last_workflow_name() == WORKFLOW_NAME
    assert registry.last_tag() == TAG
    assert registry.last_workflow_id() == wf_id
    assert registry.last_status() == STATUS_ACTIVE
    assert registry.last_don_family() == DON_FAMILY
    assert registry.last_binary_url() == BINARY_URL
    assert registry.last_config_url() == CONFIG_URL
    assert registry.last_keep_alive() is False


def test_approve_binary_stores_url_and_tag(proxy, ownership_admin):
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, approved_id(proxy), BINARY_URL, CONFIG_URL, b"", False)

    assert proxy.binary_url() == BINARY_URL
    assert proxy.approved_tag() == TAG


def test_approve_binary_rejects_empty_url(proxy, ownership_admin):
    with boa.env.prank(ownership_admin), boa.reverts("Binary URL not set"):
        proxy.approve_binary(TAG, EMPTY_BYTES32, "", CONFIG_URL, b"", False)


def test_config_update_before_any_approval_reverts(proxy, parameter_admin):
    """Nothing to inherit, so there is nothing the parameter admin could be bound to."""
    with boa.env.prank(parameter_admin), boa.reverts("No approved binary"):
        proxy.update_config(EMPTY_BYTES32, CONFIG_URL, b"", False)


def test_config_update_keeps_approved_binary(approved, registry, parameter_admin):
    """The whole point: a config swap carries the DAO's binary, whatever the caller wanted."""
    wf_id = _new_config_id(approved)

    with boa.env.prank(parameter_admin):
        approved.update_config(wf_id, NEW_CONFIG_URL, b"", False)

    assert registry.last_binary_url() == BINARY_URL
    assert registry.last_config_url() == NEW_CONFIG_URL
    assert registry.last_workflow_id() == wf_id
    assert registry.upsert_count() == 2


def test_config_update_lands_on_the_approved_tag(approved, registry, parameter_admin):
    """Regression: update_config has no tag argument, so it can only ever update the DAO's key."""
    with boa.env.prank(parameter_admin):
        approved.update_config(_new_config_id(approved), NEW_CONFIG_URL, b"", False)

    assert registry.last_tag() == TAG
    assert registry.upsert_count() == 2  # updated the one entry, did not add a second


def test_config_update_cannot_smuggle_a_binary(approved, registry, parameter_admin):
    """A parameter admin registering an id derived from other code fails closed, not open."""
    rogue_id = workflow_id(approved.address, WORKFLOW_NAME, ROGUE_WASM, NEW_CONFIG)

    with boa.env.prank(parameter_admin):
        approved.update_config(rogue_id, NEW_CONFIG_URL, b"", False)

    assert registry.last_binary_url() == BINARY_URL
    assert registry.last_binary_url() != ROGUE_BINARY_URL

    # What a node would compute from the artifacts it actually fetches
    honest_id = workflow_id(approved.address, WORKFLOW_NAME, WASM, NEW_CONFIG)
    assert registry.last_workflow_id() != honest_id


def test_update_config_while_paused_stays_paused(
    approved, registry, emergency_admin, parameter_admin
):
    """Regression: the registry rejects a status change on update, so the write must carry it."""
    with boa.env.prank(emergency_admin):
        approved.pause_workflow(approved_id(approved))

    with boa.env.prank(parameter_admin):
        approved.update_config(_new_config_id(approved), NEW_CONFIG_URL, b"", False)

    assert registry.last_status() == STATUS_PAUSED


def test_approve_binary_while_paused_stays_paused(
    approved, registry, emergency_admin, ownership_admin
):
    """Shipping a fix mid-incident must not revert; the DAO activates afterwards, in the same vote."""
    with boa.env.prank(emergency_admin):
        approved.pause_workflow(approved_id(approved))

    with boa.env.prank(ownership_admin):
        approved.approve_binary(
            TAG, _new_config_id(approved), BINARY_URL, NEW_CONFIG_URL, b"", False
        )

    assert registry.last_status() == STATUS_PAUSED

    with boa.env.prank(ownership_admin):
        approved.activate_workflow(_new_config_id(approved))

    assert registry.activated_id() == _new_config_id(approved)


def test_parameter_admin_cannot_undo_a_pause(approved, registry, emergency_admin, parameter_admin):
    """The emergency lever has to be authoritative, not a race between two multisigs."""
    wf_id = approved_id(approved)
    with boa.env.prank(emergency_admin):
        approved.pause_workflow(wf_id)

    with boa.env.prank(parameter_admin):
        approved.update_config(_new_config_id(approved), NEW_CONFIG_URL, b"", False)

    key = registry.key_of_id(_new_config_id(approved))
    assert registry.workflows(key)[3] == STATUS_PAUSED


def test_delete_clears_the_approval(approved, ownership_admin, parameter_admin):
    """Regression: a retired workflow must not be resurrectable by the parameter admin."""
    with boa.env.prank(ownership_admin):
        approved.delete_workflow(approved_id(approved))

    assert approved.binary_url() == ""
    assert approved.approved_tag() == ""

    with boa.env.prank(parameter_admin), boa.reverts("No approved binary"):
        approved.update_config(_new_config_id(approved), NEW_CONFIG_URL, b"", False)


def test_revoke_binary_without_touching_the_registry(
    approved, registry, ownership_admin, parameter_admin
):
    with boa.env.prank(ownership_admin):
        approved.revoke_binary()

    assert approved.binary_url() == ""
    assert registry.deleted_id() == EMPTY_BYTES32

    with boa.env.prank(parameter_admin), boa.reverts("No approved binary"):
        approved.update_config(_new_config_id(approved), NEW_CONFIG_URL, b"", False)


def test_set_don_family_moves_it(approved, registry, ownership_admin):
    """Regression: upsert cannot change the family, so this has its own registry call."""
    wf_id = approved_id(approved)

    with boa.env.prank(ownership_admin):
        approved.set_don_family(wf_id, "other-family")

    assert approved.don_family() == "other-family"
    key = registry.key_of_id(wf_id)
    assert registry.workflows(key)[9] == "other-family"


def test_workflow_id_binds_the_owner(approved, alice):
    """Re-registering under a different owner yields a different id, which is why the registry has"""
    as_proxy = workflow_id(approved.address, WORKFLOW_NAME, WASM, CONFIG)
    as_alice = workflow_id(alice, WORKFLOW_NAME, WASM, CONFIG)

    assert as_proxy != as_alice


def test_pause_forwards(approved, registry, emergency_admin):
    wf_id = approved_id(approved)

    with boa.env.prank(emergency_admin):
        approved.pause_workflow(wf_id)

    assert registry.paused_id() == wf_id


def test_activate_forwards_current_don_family(approved, registry, emergency_admin):
    wf_id = approved_id(approved)

    with boa.env.prank(emergency_admin):
        approved.activate_workflow(wf_id)

    assert registry.activated_id() == wf_id
    assert registry.activated_don_family() == DON_FAMILY


def test_delete_forwards(approved, registry, ownership_admin):
    wf_id = approved_id(approved)

    with boa.env.prank(ownership_admin):
        approved.delete_workflow(wf_id)

    assert registry.deleted_id() == wf_id


def test_link_owner_registers_the_proxy(proxy, registry, ownership_admin):
    """The registry takes no owner argument anywhere: ownership is msg.sender."""
    with boa.env.prank(ownership_admin):
        proxy.link_owner(2**32, EMPTY_BYTES32, b"\x01" * 65)

    assert registry.linked_owner() == proxy.address


def test_unlink_owner_passes_the_proxy(proxy, registry, ownership_admin):
    with boa.env.prank(ownership_admin):
        proxy.unlink_owner(2**32, b"\x01" * 65)

    assert registry.unlinked_owner() == proxy.address


def test_allowlist_request_forwards(proxy, registry, ownership_admin):
    digest = boa.eval("keccak256(b'request')")

    with boa.env.prank(ownership_admin):
        proxy.allowlist_request(digest, 600)

    assert registry.allowlisted_digest() == digest
    assert registry.allowlist_expiry() == 600
