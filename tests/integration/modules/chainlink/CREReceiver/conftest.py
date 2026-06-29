import boa
import hashlib
import pytest

EMPTY_ADDRESS = boa.eval("empty(address)")


def encode_metadata(
    workflow_id: bytes = None,
    workflow_name: bytes = None,
    workflow_owner: str = None,
) -> bytes:
    """
    Build the 62-byte metadata payload that CREReceiver._decode_metadata expects:
        [0:32]  workflow_id    (bytes32)
        [32:42] workflow_name  (bytes10)
        [42:62] workflow_owner (address as 20 raw bytes)
    """
    workflow_id = workflow_id or bytes(32)
    workflow_name = workflow_name or bytes(10)
    if workflow_owner is None:
        owner_bytes = bytes(20)
    else:
        owner_bytes = bytes.fromhex(workflow_owner.replace("0x", ""))
    return workflow_id + workflow_name + owner_bytes


def compute_workflow_name_bytes(name: str) -> bytes:
    """
    Python mirror of CREReceiver's name-hashing:
        sha256(name) → first 5 bytes → hex-encode → 10 ASCII bytes (bytes10)
    """
    return hashlib.sha256(name.encode()).digest()[:5].hex().encode("ascii")


_CRE_RECEIVER_WRAPPER = """
from snekmate.auth import ownable
from contracts.modules.chainlink import CREReceiver

initializes: ownable
initializes: CREReceiver[ownable:=ownable]

exports: (
    ownable.owner,
    ownable.transfer_ownership,
    ownable.renounce_ownership,
)
exports: (
    CREReceiver.set_forwarder_address,
    CREReceiver.set_expected_author,
    CREReceiver.set_expected_workflow_name,
    CREReceiver.set_expected_workflow_id,
    CREReceiver.forwarder_address,
    CREReceiver.expected_author,
    CREReceiver.expected_workflow_name,
    CREReceiver.expected_workflow_id,
    CREReceiver.supportsInterface,
)

@deploy
def __init__():
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)

@external
@payable
def onReport(
    _metadata: Bytes[CREReceiver.MAX_METADATA_SIZE],
    _report: Bytes[CREReceiver.MAX_REPORT_SIZE],
):
    CREReceiver._on_report(_metadata, _report)
"""


@pytest.fixture()
def cre_receiver(dev_deployer):
    """CREReceiver module wrapper — all tests are pure logic, no fork needed."""
    with boa.env.prank(dev_deployer):
        return boa.loads(_CRE_RECEIVER_WRAPPER)
