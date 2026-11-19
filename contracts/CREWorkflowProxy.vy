# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title CRE Workflow Proxy

@notice Owns a CRE workflow in Chainlink's WorkflowRegistry so a DAO vote, not a hot key, picks the
WASM: ownership approves binaries, parameter swaps only the config, emergency pauses.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""


################################################################
#                           INTERFACES                         #
################################################################

from .modules.chainlink.src import IWorkflowRegistry


################################################################
#                           CONSTANTS                          #
################################################################

# Must equal IWorkflowRegistry's MAX_*_SIZE, which sit above the registry's own getConfig() caps;
# a .vyi does not export constants, so these are restated and guarded by test_interface_sizes_match
MAX_NAME: constant(uint256) = 128
MAX_TAG: constant(uint256) = 128
MAX_DON_FAMILY: constant(uint256) = 64
MAX_URL: constant(uint256) = 256
MAX_ATTRIBUTES: constant(uint256) = 1024
MAX_SIGNATURE: constant(uint256) = 65

# WorkflowRegistry.WorkflowStatus
STATUS_ACTIVE: public(constant(uint8)) = 0
STATUS_PAUSED: public(constant(uint8)) = 1

# getWorkflow returns one dynamic struct: an offset word, then workflowId, owner, createdAt, status
STATUS_OFFSET: constant(uint256) = 128
GET_WORKFLOW_OUTSIZE: constant(uint256) = 160

GET_WORKFLOW_SELECTOR: constant(Bytes[4]) = method_id("getWorkflow(address,string,string)")


################################################################
#                            STORAGE                           #
################################################################

registry: public(immutable(IWorkflowRegistry))

# Hashed into every workflow id this proxy registers, so it is fixed for the proxy's life
workflow_name: public(immutable(String[MAX_NAME]))

# The DAO's approval; the parameter admin picks the config and nothing else
binary_url: public(String[MAX_URL])
approved_tag: public(String[MAX_TAG])
don_family: public(String[MAX_DON_FAMILY])

ownership_admin: public(address)
parameter_admin: public(address)
emergency_admin: public(address)

future_ownership_admin: public(address)
future_parameter_admin: public(address)
future_emergency_admin: public(address)


################################################################
#                            EVENTS                            #
################################################################

event CommitAdmins:
    ownership_admin: address
    parameter_admin: address
    emergency_admin: address

event ApplyAdmins:
    ownership_admin: address
    parameter_admin: address
    emergency_admin: address

event ApproveBinary:
    workflow_id: indexed(bytes32)
    binary_url: String[MAX_URL]
    config_url: String[MAX_URL]
    tag: String[MAX_TAG]

event UpdateConfig:
    workflow_id: indexed(bytes32)
    config_url: String[MAX_URL]

event RevokeBinary:
    pass

event SetDonFamily:
    workflow_id: indexed(bytes32)
    don_family: String[MAX_DON_FAMILY]

event PauseWorkflow:
    workflow_id: indexed(bytes32)

event ActivateWorkflow:
    workflow_id: indexed(bytes32)

event DeleteWorkflow:
    workflow_id: indexed(bytes32)


################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__(
    _registry: address,
    _workflow_name: String[MAX_NAME],
    _don_family: String[MAX_DON_FAMILY],
    _ownership_admin: address,
    _parameter_admin: address,
    _emergency_admin: address,
):
    """
    @notice Initialize the proxy; registry and workflow name are fixed at deploy
    """
    assert _registry != empty(address), "Registry not set"
    assert len(_workflow_name) != 0, "Workflow name not set"
    assert _ownership_admin != empty(address), "Ownership admin not set"
    assert _parameter_admin != empty(address), "Parameter admin not set"
    assert _emergency_admin != empty(address), "Emergency admin not set"

    registry = IWorkflowRegistry(_registry)
    workflow_name = _workflow_name

    self.don_family = _don_family
    self.ownership_admin = _ownership_admin
    self.parameter_admin = _parameter_admin
    self.emergency_admin = _emergency_admin


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
@view
def _current_status(_tag: String[MAX_TAG]) -> uint8:
    """
    @dev The registry rejects a status change on update, so a write carries the stored one forward
    """
    success: bool = False
    response: Bytes[GET_WORKFLOW_OUTSIZE] = b""
    success, response = raw_call(
        registry.address,
        concat(
            GET_WORKFLOW_SELECTOR,
            abi_encode(self, workflow_name, _tag),
        ),
        max_outsize=GET_WORKFLOW_OUTSIZE,
        is_static_call=True,
        revert_on_failure=False,
    )

    # A key that does not exist yet makes getWorkflow revert, which is the insert case
    if not success or len(response) < GET_WORKFLOW_OUTSIZE:
        return STATUS_ACTIVE

    return convert(extract32(response, STATUS_OFFSET, output_type=uint256), uint8)


@internal
def _upsert(
    _workflow_id: bytes32,
    _config_url: String[MAX_URL],
    _attributes: Bytes[MAX_ATTRIBUTES],
    _keep_alive: bool,
):
    """
    @dev The single path to the registry; everything but the config comes from storage
    """
    binary_url: String[MAX_URL] = self.binary_url
    assert len(binary_url) != 0, "No approved binary"

    tag: String[MAX_TAG] = self.approved_tag

    extcall registry.upsertWorkflow(
        workflow_name,
        tag,
        _workflow_id,
        self._current_status(tag),
        self.don_family,
        binary_url,
        _config_url,
        _attributes,
        _keep_alive,
    )


################################################################
#                     OWNERSHIP ADMIN                          #
################################################################

@external
def approve_binary(
    _tag: String[MAX_TAG],
    _workflow_id: bytes32,
    _binary_url: String[MAX_URL],
    _config_url: String[MAX_URL],
    _attributes: Bytes[MAX_ATTRIBUTES],
    _keep_alive: bool,
):
    """
    @notice Approve a WASM binary and register it, replacing whatever was approved before
    @dev Voters verify by checking sha256(proxy ++ name ++ wasm ++ config ++ "") == `_workflow_id`
    """
    assert msg.sender == self.ownership_admin, "Access denied"
    assert len(_binary_url) != 0, "Binary URL not set"

    self.binary_url = _binary_url
    self.approved_tag = _tag

    self._upsert(_workflow_id, _config_url, _attributes, _keep_alive)

    log ApproveBinary(
        workflow_id=_workflow_id,
        binary_url=_binary_url,
        config_url=_config_url,
        tag=_tag,
    )


@external
def revoke_binary():
    """
    @notice Withdraw the approval without touching the registry
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    self.binary_url = ""
    self.approved_tag = ""

    log RevokeBinary()


@external
def set_don_family(_workflow_id: bytes32, _don_family: String[MAX_DON_FAMILY]):
    """
    @notice Move the workflow to another DON family, which upsert cannot do
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    self.don_family = _don_family
    extcall registry.updateWorkflowDONFamily(_workflow_id, _don_family)

    log SetDonFamily(workflow_id=_workflow_id, don_family=_don_family)


@external
def link_owner(_validity_timestamp: uint256, _proof: bytes32, _signature: Bytes[MAX_SIGNATURE]):
    """
    @notice Register this proxy as a workflow owner, using a proof Chainlink issues for its address
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    extcall registry.linkOwner(_validity_timestamp, _proof, _signature)


@external
def unlink_owner(_validity_timestamp: uint256, _signature: Bytes[MAX_SIGNATURE]):
    """
    @notice Give up the ownership link; there is no per-workflow transfer, so migrating re-registers
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    extcall registry.unlinkOwner(self, _validity_timestamp, _signature)


@external
def allowlist_request(_request_digest: bytes32, _expiry_timestamp: uint32):
    """
    @notice Allowlist a request digest, where the registry is configured to demand one
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    extcall registry.allowlistRequest(_request_digest, _expiry_timestamp)


@external
def delete_workflow(_workflow_id: bytes32):
    """
    @notice Permanently remove a workflow, dropping the approval so it cannot be re-registered
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    self.binary_url = ""
    self.approved_tag = ""

    extcall registry.deleteWorkflow(_workflow_id)

    log DeleteWorkflow(workflow_id=_workflow_id)


@external
def commit_set_admins(_o_admin: address, _p_admin: address, _e_admin: address):
    """
    @notice Set ownership admin to `_o_admin`, parameter admin to `_p_admin` and emergency admin to `_e_admin`
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    self.future_ownership_admin = _o_admin
    self.future_parameter_admin = _p_admin
    self.future_emergency_admin = _e_admin

    log CommitAdmins(ownership_admin=_o_admin, parameter_admin=_p_admin, emergency_admin=_e_admin)


@external
def apply_set_admins():
    """
    @notice Apply the effects of `commit_set_admins`
    """
    assert msg.sender == self.ownership_admin, "Access denied"

    _o_admin: address = self.future_ownership_admin
    _p_admin: address = self.future_parameter_admin
    _e_admin: address = self.future_emergency_admin
    self.ownership_admin = _o_admin
    self.parameter_admin = _p_admin
    self.emergency_admin = _e_admin

    log ApplyAdmins(ownership_admin=_o_admin, parameter_admin=_p_admin, emergency_admin=_e_admin)


################################################################
#                     PARAMETER ADMIN                          #
################################################################

@external
def update_config(
    _workflow_id: bytes32,
    _config_url: String[MAX_URL],
    _attributes: Bytes[MAX_ATTRIBUTES],
    _keep_alive: bool,
):
    """
    @notice Point the workflow at a new config, keeping the approved binary
    @dev No tag argument on purpose: a caller-chosen tag would insert a second live entry instead
    """
    assert msg.sender == self.parameter_admin, "Access denied"

    self._upsert(_workflow_id, _config_url, _attributes, _keep_alive)

    log UpdateConfig(workflow_id=_workflow_id, config_url=_config_url)


################################################################
#                     EMERGENCY ADMIN                          #
################################################################

@external
def pause_workflow(_workflow_id: bytes32):
    """
    @notice Stop the workflow without a vote, the only lever here that is fast by design
    """
    assert msg.sender == self.emergency_admin, "Access denied"

    extcall registry.pauseWorkflow(_workflow_id)

    log PauseWorkflow(workflow_id=_workflow_id)


@external
def activate_workflow(_workflow_id: bytes32):
    """
    @notice Restart a paused workflow; either admin, so a false alarm costs no governance cycle
    """
    assert msg.sender == self.emergency_admin or msg.sender == self.ownership_admin, "Access denied"

    extcall registry.activateWorkflow(_workflow_id, self.don_family)

    log ActivateWorkflow(workflow_id=_workflow_id)
