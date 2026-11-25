"""The real WorkflowRegistry's rules, checked against the deployed mainnet contract."""

import boa
import pytest

from conftest import (
    BINARY_URL,
    CONFIG_URL,
    DON_FAMILY,
    NEW_CONFIG_URL,
    OTHER_DON_FAMILY,
    STATUS_ACTIVE,
    STATUS_PAUSED,
    TAG,
    WORKFLOW_NAME,
    WORKFLOW_REGISTRY,
    proxy_bounds,
    wid,
)


def _upsert(registry, owner, tag, workflow_id, status, don_family, config_url, keep_alive=True):
    with boa.env.prank(owner):
        registry.upsertWorkflow(
            WORKFLOW_NAME,
            tag,
            workflow_id,
            status,
            don_family,
            BINARY_URL,
            config_url,
            b"",
            keep_alive,
        )


def test_registry_is_the_expected_deployment(registry):
    assert registry.typeAndVersion() == "WorkflowRegistry 2.0.0"


def test_proxy_bounds_are_not_below_the_registry_caps(registry):
    """The proxy's String/Bytes bounds must not undercut getConfig()."""
    max_name, max_tag, max_url, max_attr, _ = registry.getConfig()
    bounds = proxy_bounds()

    assert bounds["MAX_NAME"] >= max_name, "MAX_NAME is below the registry's maxNameLen"
    assert bounds["MAX_TAG"] >= max_tag, "MAX_TAG is below the registry's maxTagLen"
    assert bounds["MAX_DON_FAMILY"] >= max_tag, "MAX_DON_FAMILY is below the registry's maxTagLen"
    assert bounds["MAX_URL"] >= max_url, "MAX_URL is below the registry's maxUrlLen"
    assert bounds["MAX_ATTRIBUTES"] >= max_attr, "MAX_ATTRIBUTES is below the registry's maxAttrLen"


def test_unlinked_caller_cannot_upsert(registry):
    """The link is the gate, which is why the proxy needs linkOwner before anything else."""
    stranger = boa.env.generate_address()
    boa.env.set_balance(stranger, 10**19)

    with boa.reverts():
        _upsert(registry, stranger, TAG, wid(1), STATUS_ACTIVE, DON_FAMILY, CONFIG_URL)


def test_insert_then_update_same_key(registry, linked_owner):
    """Baseline: a second upsert on the same (name, tag) updates rather than duplicating."""
    _upsert(registry, linked_owner, TAG, wid(10), STATUS_ACTIVE, DON_FAMILY, CONFIG_URL)
    stored = registry.getWorkflow(linked_owner, WORKFLOW_NAME, TAG)
    assert stored[3] == STATUS_ACTIVE
    assert stored[6] == CONFIG_URL

    _upsert(registry, linked_owner, TAG, wid(11), STATUS_ACTIVE, DON_FAMILY, NEW_CONFIG_URL)
    stored = registry.getWorkflow(linked_owner, WORKFLOW_NAME, TAG)
    assert stored[0] == wid(11)
    assert stored[6] == NEW_CONFIG_URL


def test_upsert_rejects_a_status_change_on_update(registry, linked_owner):
    """Finding 2's premise. A paused workflow cannot be updated with status ACTIVE."""
    _upsert(registry, linked_owner, TAG, wid(20), STATUS_ACTIVE, DON_FAMILY, CONFIG_URL)

    with boa.env.prank(linked_owner):
        registry.pauseWorkflow(wid(20))
    assert registry.getWorkflow(linked_owner, WORKFLOW_NAME, TAG)[3] == STATUS_PAUSED

    with boa.reverts():
        _upsert(registry, linked_owner, TAG, wid(21), STATUS_ACTIVE, DON_FAMILY, NEW_CONFIG_URL)

    # Carrying the stored status through is what the proxy's _current_status exists to do
    _upsert(registry, linked_owner, TAG, wid(22), STATUS_PAUSED, DON_FAMILY, NEW_CONFIG_URL)
    stored = registry.getWorkflow(linked_owner, WORKFLOW_NAME, TAG)
    assert stored[0] == wid(22)
    assert stored[3] == STATUS_PAUSED


def test_upsert_rejects_a_don_family_change_on_update(registry, linked_owner):
    """Finding 4's premise. approve_binary cannot move the family; set_don_family has to."""
    _upsert(registry, linked_owner, TAG, wid(30), STATUS_ACTIVE, DON_FAMILY, CONFIG_URL)

    with boa.reverts():
        _upsert(registry, linked_owner, TAG, wid(31), STATUS_ACTIVE, OTHER_DON_FAMILY, CONFIG_URL)


def test_a_fresh_tag_is_an_insert_not_an_update(registry, linked_owner):
    """Finding 1's premise, and why update_config has no tag argument."""
    _upsert(registry, linked_owner, TAG, wid(40), STATUS_ACTIVE, DON_FAMILY, CONFIG_URL)
    with boa.env.prank(linked_owner):
        registry.pauseWorkflow(wid(40))
    assert registry.getWorkflow(linked_owner, WORKFLOW_NAME, TAG)[3] == STATUS_PAUSED

    _upsert(registry, linked_owner, "rogue", wid(41), STATUS_ACTIVE, DON_FAMILY, NEW_CONFIG_URL)

    assert registry.getWorkflow(linked_owner, WORKFLOW_NAME, TAG)[3] == STATUS_PAUSED
    assert registry.getWorkflow(linked_owner, WORKFLOW_NAME, "rogue")[3] == STATUS_ACTIVE


# ── The proxy itself, against the real registry ──────────────────────────────


@pytest.fixture()
def proxy(linked_owner, ownership_admin, parameter_admin, emergency_admin, dev_deployer):
    """The real proxy, deployed onto an address the registry has already linked."""
    with boa.env.prank(dev_deployer):
        return boa.load_partial("contracts/CREWorkflowProxy.vy").deploy(
            WORKFLOW_REGISTRY,
            WORKFLOW_NAME,
            DON_FAMILY,
            ownership_admin,
            parameter_admin,
            emergency_admin,
            override_address=linked_owner,
        )


@pytest.fixture()
def ownership_admin():
    return boa.env.generate_address()


@pytest.fixture()
def parameter_admin():
    return boa.env.generate_address()


@pytest.fixture()
def emergency_admin():
    return boa.env.generate_address()


def test_proxy_approves_a_binary_on_the_real_registry(proxy, registry, ownership_admin):
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, wid(50), BINARY_URL, CONFIG_URL, b"", True)

    stored = registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)
    assert stored[0] == wid(50)
    assert stored[1] == proxy.address
    assert stored[3] == STATUS_ACTIVE
    assert stored[5] == BINARY_URL
    assert stored[9] == DON_FAMILY


def test_proxy_carries_the_paused_status_through(
    proxy, registry, ownership_admin, emergency_admin, parameter_admin
):
    """The incident sequence, end to end: pause, ship a fix, restart - no revert anywhere."""
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, wid(60), BINARY_URL, CONFIG_URL, b"", True)

    with boa.env.prank(emergency_admin):
        proxy.pause_workflow(wid(60))
    assert registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)[3] == STATUS_PAUSED

    # A config swap while paused stays paused rather than reverting or silently restarting
    with boa.env.prank(parameter_admin):
        proxy.update_config(wid(61), NEW_CONFIG_URL, b"", True)
    stored = registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)
    assert stored[0] == wid(61)
    assert stored[3] == STATUS_PAUSED

    # The DAO ships the corrected binary, still paused
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, wid(62), BINARY_URL, CONFIG_URL, b"", True)
    assert registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)[3] == STATUS_PAUSED

    # and only then restarts it, which fits in the same vote script
    with boa.env.prank(ownership_admin):
        proxy.activate_workflow(wid(62))
    assert registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)[3] == STATUS_ACTIVE


def test_parameter_admin_cannot_escape_the_approved_tag(
    proxy, registry, ownership_admin, emergency_admin, parameter_admin
):
    """The fix for finding 1, against the real registry."""
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, wid(70), BINARY_URL, CONFIG_URL, b"", True)
    with boa.env.prank(emergency_admin):
        proxy.pause_workflow(wid(70))

    with boa.env.prank(parameter_admin):
        proxy.update_config(wid(71), NEW_CONFIG_URL, b"", True)

    assert registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)[3] == STATUS_PAUSED
    assert registry.totalActiveWorkflowsByOwner(proxy.address) == 0


# MaxWorkflowsPerUserDONExceeded(address,string)
QUOTA_ERROR = bytes.fromhex("038857ff")


def test_proxy_set_don_family_reaches_the_registry(proxy, registry, ownership_admin):
    """approve_binary cannot change the family, so the dedicated call has to work."""
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, wid(80), BINARY_URL, CONFIG_URL, b"", True)

    if registry.getMaxWorkflowsPerUserDON(proxy.address, OTHER_DON_FAMILY) > 0:
        with boa.env.prank(ownership_admin):
            proxy.set_don_family(wid(80), OTHER_DON_FAMILY)

        assert registry.getWorkflow(proxy.address, WORKFLOW_NAME, TAG)[9] == OTHER_DON_FAMILY
        assert proxy.don_family() == OTHER_DON_FAMILY
        return

    with pytest.raises(Exception) as excinfo:
        with boa.env.prank(ownership_admin):
            proxy.set_don_family(wid(80), OTHER_DON_FAMILY)

    assert QUOTA_ERROR in _revert_data(excinfo.value), "expected the per-user DON quota error"
    # The failed call rolled back, so the proxy did not drift from the registry
    assert proxy.don_family() == DON_FAMILY


def _revert_data(error) -> bytes:
    """Pull the raw revert payload out of the frames boa wrapped it in."""
    found = b""
    for frame in getattr(error, "args", ()):
        computation = getattr(frame, "computation", None)
        if computation is None:
            continue
        output = getattr(computation, "output", b"")
        if isinstance(output, bytes) and output:
            found += output
        for vm_arg in getattr(getattr(computation, "error", None), "args", ()):
            if isinstance(vm_arg, bytes):
                found += vm_arg
    return found
