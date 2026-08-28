"""Every entry point's role gate, one test per caller that must be turned away."""

import boa
import pytest

from conftest import (
    BINARY_URL,
    CONFIG,
    CONFIG_URL,
    DON_FAMILY,
    EMPTY_BYTES32,
    TAG,
    WASM,
    WORKFLOW_NAME,
    workflow_id,
)


def _approve(proxy, caller, wf_id):
    with boa.env.prank(caller):
        proxy.approve_binary(TAG, wf_id, BINARY_URL, CONFIG_URL, b"", False)


@pytest.fixture()
def wf_id(proxy):
    return workflow_id(proxy.address, WORKFLOW_NAME, WASM, CONFIG)


def test_approve_binary_is_ownership_only(proxy, wf_id, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.reverts("Access denied"):
            _approve(proxy, caller, wf_id)


def test_update_config_is_parameter_only(approved, wf_id, ownership_admin, emergency_admin, alice):
    """Ownership is deliberately excluded: it changes config through approve_binary."""
    for caller in (ownership_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            approved.update_config(wf_id, CONFIG_URL, b"", False)


def test_revoke_binary_is_ownership_only(approved, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            approved.revoke_binary()


def test_set_don_family_is_ownership_only(approved, wf_id, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            approved.set_don_family(wf_id, "other-family")


def test_pause_is_emergency_only(approved, wf_id, ownership_admin, parameter_admin, alice):
    for caller in (ownership_admin, parameter_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            approved.pause_workflow(wf_id)


def test_activate_allows_emergency_and_ownership(
    approved, registry, wf_id, ownership_admin, emergency_admin
):
    """Mirrors PoolProxy.unkill_me: a false alarm should not cost a governance cycle."""
    with boa.env.prank(emergency_admin):
        approved.activate_workflow(wf_id)
    assert registry.activated_id() == wf_id

    with boa.env.prank(ownership_admin):
        approved.activate_workflow(wf_id)
    assert registry.activated_id() == wf_id


def test_activate_rejects_parameter_admin(approved, wf_id, parameter_admin, alice):
    for caller in (parameter_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            approved.activate_workflow(wf_id)


def test_delete_is_ownership_only(approved, wf_id, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            approved.delete_workflow(wf_id)


def test_link_owner_is_ownership_only(proxy, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            proxy.link_owner(0, EMPTY_BYTES32, b"")


def test_unlink_owner_is_ownership_only(proxy, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            proxy.unlink_owner(0, b"")


def test_allowlist_request_is_ownership_only(proxy, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            proxy.allowlist_request(EMPTY_BYTES32, 0)


def test_commit_set_admins_is_ownership_only(proxy, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            proxy.commit_set_admins(caller, caller, caller)


def test_apply_set_admins_is_ownership_only(proxy, parameter_admin, emergency_admin, alice):
    for caller in (parameter_admin, emergency_admin, alice):
        with boa.env.prank(caller), boa.reverts("Access denied"):
            proxy.apply_set_admins()


def test_set_admins_is_two_step(proxy, ownership_admin, alice):
    with boa.env.prank(ownership_admin):
        proxy.commit_set_admins(alice, alice, alice)

    assert proxy.ownership_admin() == ownership_admin
    assert proxy.future_ownership_admin() == alice

    with boa.env.prank(ownership_admin):
        proxy.apply_set_admins()

    assert proxy.ownership_admin() == alice
    assert proxy.parameter_admin() == alice
    assert proxy.emergency_admin() == alice


def test_old_ownership_admin_loses_access(proxy, ownership_admin, alice, wf_id):
    with boa.env.prank(ownership_admin):
        proxy.commit_set_admins(alice, alice, alice)
        proxy.apply_set_admins()

    with boa.reverts("Access denied"):
        _approve(proxy, ownership_admin, wf_id)

    _approve(proxy, alice, wf_id)
    assert proxy.binary_url() == BINARY_URL


def test_don_family_survives_a_deploy(proxy):
    """Constructor value, not something a later caller supplies to approve_binary."""
    assert proxy.don_family() == DON_FAMILY
