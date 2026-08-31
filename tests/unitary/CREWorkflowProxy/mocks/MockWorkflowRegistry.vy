# pragma version 0.4.3

"""
@title Mock Workflow Registry

@notice Keyed stand-in for Chainlink's WorkflowRegistry: enough state to enforce the update rules
the proxy relies on - CannotChangeStatusOnUpdate, CannotChangeDONFamilyOnUpdate, WorkflowDoesNotExist.
"""

MAX_NAME: constant(uint256) = 128
MAX_TAG: constant(uint256) = 128
MAX_DON_FAMILY: constant(uint256) = 64
MAX_URL: constant(uint256) = 256
MAX_ATTRIBUTES: constant(uint256) = 1024
MAX_SIGNATURE: constant(uint256) = 65
MAX_TAGS_PER_NAME: constant(uint256) = 8

STATUS_ACTIVE: constant(uint8) = 0
STATUS_PAUSED: constant(uint8) = 1

# Field order must match the real ABI: the proxy reads `status` out of the head by offset
struct WorkflowMetadataView:
    workflowId: bytes32
    owner: address
    createdAt: uint64
    status: uint8
    workflowName: String[MAX_NAME]
    binaryUrl: String[MAX_URL]
    configUrl: String[MAX_URL]
    tag: String[MAX_TAG]
    attributes: Bytes[MAX_ATTRIBUTES]
    donFamily: String[MAX_DON_FAMILY]


workflows: public(HashMap[bytes32, WorkflowMetadataView])  # key = hash(owner, name, tag)
exists: public(HashMap[bytes32, bool])
key_of_id: public(HashMap[bytes32, bytes32])  # workflowId -> key
tags_of_name: HashMap[bytes32, DynArray[String[MAX_TAG], MAX_TAGS_PER_NAME]]

linked_owner: public(address)
unlinked_owner: public(address)

upsert_count: public(uint256)
last_caller: public(address)
last_workflow_name: public(String[MAX_NAME])
last_tag: public(String[MAX_TAG])
last_workflow_id: public(bytes32)
last_status: public(uint8)
last_don_family: public(String[MAX_DON_FAMILY])
last_binary_url: public(String[MAX_URL])
last_config_url: public(String[MAX_URL])
last_attributes: public(Bytes[MAX_ATTRIBUTES])
last_keep_alive: public(bool)

paused_id: public(bytes32)
activated_id: public(bytes32)
activated_don_family: public(String[MAX_DON_FAMILY])
deleted_id: public(bytes32)

allowlisted_digest: public(bytes32)
allowlist_expiry: public(uint32)


@internal
@pure
def _key(owner: address, name: String[MAX_NAME], tag: String[MAX_TAG]) -> bytes32:
    return keccak256(abi_encode(owner, name, tag))


@external
def linkOwner(validityTimestamp: uint256, proof: bytes32, signature: Bytes[MAX_SIGNATURE]):
    self.linked_owner = msg.sender


@external
def unlinkOwner(owner: address, validityTimestamp: uint256, signature: Bytes[MAX_SIGNATURE]):
    self.unlinked_owner = owner


@external
def upsertWorkflow(
    workflowName: String[MAX_NAME],
    tag: String[MAX_TAG],
    workflowId: bytes32,
    status: uint8,
    donFamily: String[MAX_DON_FAMILY],
    binaryUrl: String[MAX_URL],
    configUrl: String[MAX_URL],
    attributes: Bytes[MAX_ATTRIBUTES],
    keepAlive: bool,
):
    key: bytes32 = self._key(msg.sender, workflowName, tag)

    if self.exists[key]:
        stored: WorkflowMetadataView = self.workflows[key]
        assert status == stored.status, "CannotChangeStatusOnUpdate"
        assert keccak256(donFamily) == keccak256(stored.donFamily), "CannotChangeDONFamilyOnUpdate"
        self.key_of_id[stored.workflowId] = empty(bytes32)
    else:
        name_key: bytes32 = keccak256(abi_encode(msg.sender, workflowName))
        tags: DynArray[String[MAX_TAG], MAX_TAGS_PER_NAME] = self.tags_of_name[name_key]

        # keepAlive false pauses the owner's other entries under the same name
        if not keepAlive:
            for sibling: String[MAX_TAG] in tags:
                sibling_key: bytes32 = self._key(msg.sender, workflowName, sibling)
                if self.exists[sibling_key]:
                    self.workflows[sibling_key].status = STATUS_PAUSED

        tags.append(tag)
        self.tags_of_name[name_key] = tags
        self.exists[key] = True

    self.workflows[key] = WorkflowMetadataView(
        workflowId=workflowId,
        owner=msg.sender,
        createdAt=convert(block.timestamp, uint64),
        status=status,
        workflowName=workflowName,
        binaryUrl=binaryUrl,
        configUrl=configUrl,
        tag=tag,
        attributes=attributes,
        donFamily=donFamily,
    )
    self.key_of_id[workflowId] = key

    self.upsert_count += 1
    self.last_caller = msg.sender
    self.last_workflow_name = workflowName
    self.last_tag = tag
    self.last_workflow_id = workflowId
    self.last_status = status
    self.last_don_family = donFamily
    self.last_binary_url = binaryUrl
    self.last_config_url = configUrl
    self.last_attributes = attributes
    self.last_keep_alive = keepAlive


@external
@view
def getWorkflow(
    owner: address, workflowName: String[MAX_NAME], tag: String[MAX_TAG]
) -> WorkflowMetadataView:
    key: bytes32 = self._key(owner, workflowName, tag)
    assert self.exists[key], "WorkflowDoesNotExist"
    return self.workflows[key]


@external
def pauseWorkflow(workflowId: bytes32):
    key: bytes32 = self.key_of_id[workflowId]
    assert key != empty(bytes32) and self.exists[key], "WorkflowDoesNotExist"

    self.workflows[key].status = STATUS_PAUSED
    self.paused_id = workflowId


@external
def activateWorkflow(workflowId: bytes32, donFamily: String[MAX_DON_FAMILY]):
    key: bytes32 = self.key_of_id[workflowId]
    assert key != empty(bytes32) and self.exists[key], "WorkflowDoesNotExist"

    self.workflows[key].status = STATUS_ACTIVE
    self.activated_id = workflowId
    self.activated_don_family = donFamily


@external
def updateWorkflowDONFamily(workflowId: bytes32, newDonFamily: String[MAX_DON_FAMILY]):
    key: bytes32 = self.key_of_id[workflowId]
    assert key != empty(bytes32) and self.exists[key], "WorkflowDoesNotExist"

    self.workflows[key].donFamily = newDonFamily


@external
def deleteWorkflow(workflowId: bytes32):
    key: bytes32 = self.key_of_id[workflowId]
    assert key != empty(bytes32) and self.exists[key], "WorkflowDoesNotExist"

    self.exists[key] = False
    self.key_of_id[workflowId] = empty(bytes32)
    self.deleted_id = workflowId


@external
def allowlistRequest(requestDigest: bytes32, expiryTimestamp: uint32):
    self.allowlisted_digest = requestDigest
    self.allowlist_expiry = expiryTimestamp
