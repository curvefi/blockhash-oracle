# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title CREReceiver - Abstract receiver with optional permission controls

@notice Provides flexible, updatable security checks for receiving workflow reports

@dev The forwarder address is required at construction time for security.
Additional permission fields can be configured using setter functions.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""


################################################################
#                           INTERFACES                         #
################################################################

from ethereum.ercs import IERC165 

implements: IERC165


################################################################
#                            MODULES                           #
################################################################

# Import ownership management
from snekmate.auth import ownable

uses: ownable


################################################################
#                           CONSTANTS                          #
################################################################

MAX_MESSAGE_SIZE: constant(uint256) = 128
HEX_CHARS: constant(String[16]) = "0123456789abcdef"

MAX_WORKFLOW_NAME_SIZE: constant(uint256) = 40
MAX_METADATA_SIZE: constant(uint256) = 64
MAX_REPORT_SIZE: constant(uint256) = 8192

# @dev Static list of supported ERC165 interface ids
SUPPORTED_INTERFACES: constant(bytes4[2]) = [
    # ERC165 interface ID of ERC165
    0x01ffc9a7,
    # ERC165 interface ID of IReceiver
    0x805f2132,
]

################################################################
#                            STORAGE                           #
################################################################

# Required permission field at deployment, configurable after
forwarder_address: public(address) # Only this address can call onReport

# Optional permission fields (all default to zero = disabled)
expected_author: public(address) # If set, only reports from this workflow owner are accepted
expected_workflow_name: public(bytes10) # Only validated when s_expectedAuthor is also set
expected_workflow_id: public(bytes32) # If set, only reports from this specific workflow ID are accepted


################################################################
#                            EVENTS                            #
################################################################

event ForwarderAddressUpdated:
    previous_forwarder: indexed(address)
    new_forwarder: indexed(address)

event ExpectedAuthorUpdated:
    previous_author: indexed(address)
    new_author: indexed(address)
    
event ExpectedWorkflowNameUpdated:
    previous_name: indexed(bytes10)
    new_name: indexed(bytes10)

event ExpectedWorkflowIdUpdated:
    previous_id: indexed(bytes32)
    new_id: indexed(bytes32)

event SecurityWarning:
    message: String[MAX_MESSAGE_SIZE]


################################################################
#                          CONSTRUCTOR                         #
################################################################

# @deploy
# def __init__(
#     _forwarder_address: address,
# ):
#     """
#     @notice Constructor configures the forwarder address
#     @dev The forwarder address is required for security - it ensures only verified reports are processed
#     @param _forwarder_address The address of the Chainlink Forwarder contract (cannot be address(0))
#     """

#     # assert _forwarder_address != empty(address), "Invalid forwarder address"
#     self.forwarder_address = _forwarder_address

#     log ForwarderAddressUpdated(
#         previous_forwarder=empty(address),
#         new_forwarder=self.forwarder_address,
#     )


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def set_forwarder_address(
    _forwarder_address: address
):
    """
    @notice Updates the forwarder address that is allowed to call onReport
    @param _forwarder_address The new forwarder address
    @dev WARNING: Setting to address(0) disables forwarder validation.
         This makes your contract INSECURE - anyone can call onReport() with arbitrary data.
         Only use address(0) if you fully understand the security implications.
    """
    ownable._check_owner()
    
    previous_forwarder: address = self.forwarder_address

    # Emit warning if disabling forwarder check
    
    # if _forwarder_address == empty(address):
    #     log SecurityWarning(
    #         message="Forwarder address set to zero - contract is now INSECURE"
    #     )

    self.forwarder_address = _forwarder_address
    log ForwarderAddressUpdated(
        previous_forwarder=previous_forwarder,
        new_forwarder=self.forwarder_address,
    )


@external
def set_expected_author(
    _expected_author: address
):
    """
    @notice Updates the expected workflow owner address
    @param _expected_author The new expected author address (use address(0) to disable this check)
    """
    ownable._check_owner()

    previous_author: address = self.expected_author

    self.expected_author = _expected_author
    log ExpectedAuthorUpdated(
        previous_author=previous_author,
        new_author=self.expected_author,
    )


@external
def set_expected_workflow_name(
    _expected_workflow_name: String[MAX_WORKFLOW_NAME_SIZE]
):
    """
    @notice Updates the expected workflow name from a plaintext string
    @param _expected_workflow_name The workflow name as a string (use empty string "" to disable this check)
    @dev IMPORTANT: Workflow name validation REQUIRES author validation to be enabled.
         The workflow name uses only 40-bit truncation, making collision attacks feasible
         when used alone. However, since workflow names are unique per owner, validating
         both the name AND the author address provides adequate security.
         You must call setExpectedAuthor() before or after calling this function.
         The name is hashed using SHA256 and truncated to bytes10.
    """
    ownable._check_owner()

    previous_workflow_name: bytes10 = self.expected_workflow_name
    
    if _expected_workflow_name == empty(String[MAX_WORKFLOW_NAME_SIZE]):
        self.expected_workflow_name = empty(bytes10)
        log ExpectedWorkflowNameUpdated(
            previous_name=previous_workflow_name, 
            new_name = self.expected_workflow_name
        )
        return

    # Convert workflow name to bytes10:
    # SHA256 hash → hex encode → take first 10 chars → hex encode those chars
    name_hash: bytes32 = sha256(_expected_workflow_name)
    hex_string: String[10]  = self._bytes_to_hex_string(slice(abi_encode(name_hash), 0, 5))
    first_10: bytes10 = convert(convert(hex_string, Bytes[10]), bytes10)
    self.expected_workflow_name = first_10
    
    log ExpectedWorkflowNameUpdated(
        previous_name=previous_workflow_name, 
        new_name = self.expected_workflow_name
    )


@external
def set_expected_workflow_id(
    _expected_workflow_id: bytes32
):
    """
    @notice Updates the expected workflow ID
    @param _expected_workflow_id The new expected workflow ID (use bytes32(0) to disable this check)
    """
    ownable._check_owner()

    previous_workflow_id: bytes32 = self.expected_workflow_id

    self.expected_workflow_id = _expected_workflow_id
    log ExpectedWorkflowIdUpdated(
        previous_id=previous_workflow_id,
        new_id=self.expected_workflow_id,
    )

# @internal
# @pure  
# def _bytes_to_hex_string(
#     data: Bytes[32]
# ) -> Bytes[64]:
#     """
#     @notice  Helper function to convert bytes to hex string
#     @param data The bytes to convert
#     @return The hex string representation
#     """

#     hex_string: Bytes[64] = b""

#     for i: uint256 in range(len(data), bound=32):
#         byte_val: uint256 = convert(slice(data, i, 1), uint256)

#         char_high: Bytes[1] = convert(slice(HEX_CHARS, byte_val >> 4, 1), Bytes[1])
#         char_low: Bytes[1] = convert(slice(HEX_CHARS, byte_val & 15, 1), Bytes[1])

#         size: uint256 = (i+1)*2
#         assert size <= 64
#         hex_string = slice(concat(hex_string, char_high, char_low), 0, size)

#     return hex_string

@internal
@pure
def _bytes_to_hex_string(data: Bytes[5]) -> String[10]:
    b0: uint256 = convert(slice(data, 0, 1), uint256)
    b1: uint256 = convert(slice(data, 1, 1), uint256)
    b2: uint256 = convert(slice(data, 2, 1), uint256)
    b3: uint256 = convert(slice(data, 3, 1), uint256)
    b4: uint256 = convert(slice(data, 4, 1), uint256)

    return concat(
        slice(HEX_CHARS, b0 >> 4, 1), slice(HEX_CHARS, b0 & 15, 1),
        slice(HEX_CHARS, b1 >> 4, 1), slice(HEX_CHARS, b1 & 15, 1),
        slice(HEX_CHARS, b2 >> 4, 1), slice(HEX_CHARS, b2 & 15, 1),
        slice(HEX_CHARS, b3 >> 4, 1), slice(HEX_CHARS, b3 & 15, 1),
        slice(HEX_CHARS, b4 >> 4, 1), slice(HEX_CHARS, b4 & 15, 1),
    )



################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################


@internal
def _on_report(metadata: Bytes[MAX_METADATA_SIZE], report: Bytes[MAX_REPORT_SIZE]):
    """
    @dev Performs optional validation checks based on which permission fields are set
    """
    
    # Security Check 1: Verify caller is the trusted Chainlink Forwarder
    assert msg.sender == self.forwarder_address, "Invalid sender"

    # Security Checks 2-4: Verify workflow identity - ID, owner, and/or name (if any are configured)
    if self.expected_workflow_id != empty(bytes32) or self.expected_author != empty(address) or self.expected_workflow_name != empty(bytes10):
        
        workflow_id: bytes32 = empty(bytes32)
        workflow_name: bytes10 = empty(bytes10)
        workflow_owner: address = empty(address)

        workflow_id, workflow_name, workflow_owner = self._decode_metadata(metadata)
        assert self.expected_workflow_id == empty(bytes32) or workflow_id == self.expected_workflow_id, "Invalid workflow id"
        assert self.expected_author == empty(address) or workflow_owner == self.expected_author, "Invalid author"

        # ================================================================
        # WORKFLOW NAME VALIDATION - REQUIRES AUTHOR VALIDATION
        # ================================================================
        # Do not rely on workflow name validation alone. Workflow names are unique
        # per owner, but not across owners.
        # Furthermore, workflow names use 40-bit truncation (bytes10), making collisions possible.
        # Therefore, workflow name validation REQUIRES author (workflow owner) validation.
        # The code enforces this dependency at runtime.
        # ================================================================
        if self.expected_workflow_name != empty(bytes10):
            # Author must be configured if workflow name is used
            assert self.expected_author != empty(address), "Workflow name requires author validation"

            # Validate workflow name matches (author already validated above)
            assert workflow_name == self.expected_workflow_name, "Invalid workflow name"
    

@internal
@pure
def _decode_metadata(metadata: Bytes[MAX_METADATA_SIZE]) -> (bytes32, bytes10, address):
    """
    @notice Extracts all metadata fields from the onReport metadata parameter
    @param metadata The metadata bytes encoded using abi.encodePacked(workflow_id, workflow_name, workflow_owner)
    @return workflow_id The unique identifier of the workflow (bytes32)
    @return workflow_name The name of the workflow (bytes10)
    @return workflow_owner The owner address of the workflow
    """

    # Metadata structure (encoded using abi.encodePacked by the Forwarder):
    # - First 32 bytes: length of the byte array (standard for dynamic bytes)
    # - Offset 32, size 32: workflow_id (bytes32)
    # - Offset 64, size 10: workflow_name (bytes10)
    # - Offset 74, size 20: workflow_owner (address)
    workflow_id: bytes32 = convert(slice(metadata, 0, 32), bytes32)
    workflow_name: bytes10 = convert(slice(metadata, 32, 10), bytes10)
    workflow_owner: address = convert(slice(metadata, 42, 20), address)
    return (workflow_id, workflow_name, workflow_owner)


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@view
@external
def supportsInterface(interface_id: bytes4) -> bool:
    """
    @dev Interface identification is specified in ERC-165.
    @param interface_id Id of the interface
    """
    return interface_id in SUPPORTED_INTERFACES
