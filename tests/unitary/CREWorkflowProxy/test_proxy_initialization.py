import re
from pathlib import Path

import boa

from conftest import (
    DON_FAMILY,
    EMPTY_ADDRESS,
    WORKFLOW_NAME,
)


def test_stores_admins(proxy, ownership_admin, parameter_admin, emergency_admin):
    assert proxy.ownership_admin() == ownership_admin
    assert proxy.parameter_admin() == parameter_admin
    assert proxy.emergency_admin() == emergency_admin


def test_stores_registry_and_name(proxy, registry):
    assert proxy.registry() == registry.address
    assert proxy.workflow_name() == WORKFLOW_NAME
    assert proxy.don_family() == DON_FAMILY


def test_starts_with_no_approved_binary(proxy):
    assert proxy.binary_url() == ""


def test_future_admins_start_empty(proxy):
    assert proxy.future_ownership_admin() == EMPTY_ADDRESS
    assert proxy.future_parameter_admin() == EMPTY_ADDRESS
    assert proxy.future_emergency_admin() == EMPTY_ADDRESS


def test_rejects_zero_registry(
    dev_deployer, proxy_deployer, ownership_admin, parameter_admin, emergency_admin
):
    with boa.env.prank(dev_deployer), boa.reverts("Registry not set"):
        proxy_deployer.deploy(
            EMPTY_ADDRESS,
            WORKFLOW_NAME,
            DON_FAMILY,
            ownership_admin,
            parameter_admin,
            emergency_admin,
        )


def test_rejects_zero_ownership_admin(
    dev_deployer, registry, proxy_deployer, parameter_admin, emergency_admin
):
    with boa.env.prank(dev_deployer), boa.reverts("Ownership admin not set"):
        proxy_deployer.deploy(
            registry.address,
            WORKFLOW_NAME,
            DON_FAMILY,
            EMPTY_ADDRESS,
            parameter_admin,
            emergency_admin,
        )


def test_rejects_zero_parameter_admin(
    dev_deployer, registry, proxy_deployer, ownership_admin, emergency_admin
):
    with boa.env.prank(dev_deployer), boa.reverts("Parameter admin not set"):
        proxy_deployer.deploy(
            registry.address,
            WORKFLOW_NAME,
            DON_FAMILY,
            ownership_admin,
            EMPTY_ADDRESS,
            emergency_admin,
        )


def test_rejects_zero_emergency_admin(
    dev_deployer, registry, proxy_deployer, ownership_admin, parameter_admin
):
    with boa.env.prank(dev_deployer), boa.reverts("Emergency admin not set"):
        proxy_deployer.deploy(
            registry.address,
            WORKFLOW_NAME,
            DON_FAMILY,
            ownership_admin,
            parameter_admin,
            EMPTY_ADDRESS,
        )


def test_interface_sizes_match():
    """The proxy restates IWorkflowRegistry's MAX_*_SIZE because a .vyi exports no constants."""
    proxy_src = Path("contracts/CREWorkflowProxy.vy").read_text(encoding="utf-8")
    iface_src = Path("contracts/modules/chainlink/src/IWorkflowRegistry.vyi").read_text(
        encoding="utf-8"
    )

    def consts(source):
        return dict(re.findall(r"^(MAX_\w+): constant\(uint256\) = (\d+)$", source, re.M))

    proxy, iface = consts(proxy_src), consts(iface_src)

    assert proxy["MAX_NAME"] == iface["MAX_NAME_SIZE"]
    assert proxy["MAX_TAG"] == iface["MAX_NAME_SIZE"]
    assert proxy["MAX_DON_FAMILY"] == iface["MAX_DON_FAMILY_SIZE"]
    assert proxy["MAX_URL"] == iface["MAX_URL_SIZE"]
    assert proxy["MAX_ATTRIBUTES"] == iface["MAX_ATTRIBUTES_SIZE"]
    assert proxy["MAX_SIGNATURE"] == iface["MAX_SIGNATURE_SIZE"]
