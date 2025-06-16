# pragma version 0.4.2

"""
@title LayerZero Read Command Codec V1
@license Copyright (c) Curve.Fi, 2025 - all rights reserved
@author curve.fi
@custom:security security@curve.fi
"""

# Vyper-specific constants
from . import VyperConstants as constants


################################################################
#                           CONSTANTS                          #
################################################################

# Vyper Byte size limits
MAX_MESSAGE_SIZE: constant(uint256) = constants.MAX_MESSAGE_SIZE
MAX_CALLDATA_SIZE: constant(uint256) = constants.MAX_CALLDATA_SIZE

MAX_EVM_CALL_REQUESTS: constant(uint256) = (MAX_MESSAGE_SIZE - 6 - 39) // (MAX_CALLDATA_SIZE + 42)
# +6 is general header, see encode()
# +39 is single compute command length, see appendEVMCallComputeV1
# +42 is per-call header length, see appendEVMCallRequestV1

# Read codec constants
CMD_VERSION: constant(uint16) = 1
REQUEST_VERSION: constant(uint8) = 1
RESOLVER_TYPE_SINGLE_VIEW_EVM_CALL: constant(uint16) = 1

COMPUTE_VERSION: constant(uint8) = 1
COMPUTE_TYPE_SINGLE_VIEW_EVM_CALL: constant(uint16) = 1

# Compute settings
COMPUTE_SETTING_MAP_ONLY: constant(uint8) = 0
COMPUTE_SETTING_REDUCE_ONLY: constant(uint8) = 1
COMPUTE_SETTING_MAP_REDUCE: constant(uint8) = 2
COMPUTE_SETTING_NONE: constant(uint8) = 3

################################################################
#                           STRUCTS                            #
################################################################

struct EVMCallRequestV1:
    appRequestLabel: uint16  # Label identifying the application or type of request (can be use in lzCompute)
    targetEid: uint32  # Target endpoint ID (representing a target blockchain)
    isBlockNum: bool  # True if the request = block number, false if timestamp
    blockNumOrTimestamp: uint64  # Block number or timestamp to use in the request
    confirmations: uint16  # Number of block confirmations on top of the requested block number or timestamp before the view function can be called
    to: address  # Address of the target contract on the target chain
    callData: Bytes[MAX_CALLDATA_SIZE]  # Calldata for the contract call


struct EVMCallComputeV1:
    computeSetting: uint8  # Compute setting (0 = map only, 1 = reduce only, 2 = map reduce)
    targetEid: uint32  # Target endpoint ID (representing a target blockchain)
    isBlockNum: bool  # True if the request = block number, false if timestamp
    blockNumOrTimestamp: uint64  # Block number or timestamp to use in the request
    confirmations: uint16  # Number of block confirmations on top of the requested block number or timestamp before the view function can be called
    to: address  # Address of the target contract on the target chain


# ################################################################
# #                     ReadCmdCodecV1 LIBRARY                   #
# ################################################################

# Vyper-specific:
# decode - not implemented
# decodeRequestsV1 - not implemented
# decodeEVMCallRequestV1 - not implemented
# decodeEVMCallComputeV1 - not implemented

@internal
@pure
def _decodeCmdAppLabel(_cmd: Bytes[MAX_MESSAGE_SIZE]) -> uint16:
    cmdVersion: uint16 = convert(slice(_cmd, 0, 2), uint16)
    assert cmdVersion == CMD_VERSION, "OApp: InvalidVersion"
    return convert(slice(_cmd, 2, 2), uint16)


@internal
@pure
def _decodeRequestV1AppRequestLabel(_request: Bytes[MAX_MESSAGE_SIZE]) -> uint16:
    requestVersion: uint8 = convert(slice(_request, 0, 1), uint8)
    assert requestVersion == REQUEST_VERSION, "OApp: InvalidVersion"
    return convert(slice(_request, 1, 2), uint16)


@internal
@pure
def encode(
    _appCmdLabel: uint16,
    _evmCallRequests: DynArray[EVMCallRequestV1, MAX_EVM_CALL_REQUESTS],
    _evmCallCompute: EVMCallComputeV1 = empty(EVMCallComputeV1),
) -> Bytes[MAX_MESSAGE_SIZE]:
    cmd: Bytes[MAX_MESSAGE_SIZE] = concat(
        convert(CMD_VERSION, bytes2),
        convert(_appCmdLabel, bytes2),
        convert(convert(len(_evmCallRequests), uint16), bytes2),
    )
    for call_request: EVMCallRequestV1 in _evmCallRequests:
        cmd = self.appendEVMCallRequestV1(cmd, call_request)

    if _evmCallCompute.targetEid != 0:
        cmd = self.appendEVMCallComputeV1(cmd, _evmCallCompute)
    return cmd


@internal
@pure
def appendEVMCallRequestV1(
    _cmd: Bytes[MAX_MESSAGE_SIZE], _request: EVMCallRequestV1
) -> Bytes[MAX_MESSAGE_SIZE]:
    """
    @notice Appends an EVM call request to the command
    @param _cmd The existing command bytes
    @param _request The EVM call request to append
    @return The updated command bytes
    """

    # dev: assert that appending new request to existing command will not exceed the max size
    assert (len(_cmd) + MAX_CALLDATA_SIZE + 42 <= MAX_MESSAGE_SIZE), "OApp: Command too large"
    # dev: 42 is length of all fields excluding existing command and callData
    return concat(
        # current cmd
        convert(_cmd, Bytes[MAX_MESSAGE_SIZE - MAX_CALLDATA_SIZE - 42]), # downcast Bytes size
        # newCmd
        convert(REQUEST_VERSION, bytes1),
        convert(_request.appRequestLabel, bytes2),
        convert(RESOLVER_TYPE_SINGLE_VIEW_EVM_CALL, bytes2),
        convert(convert(len(_request.callData) + 35, uint16), bytes2),
        convert(_request.targetEid, bytes4),
        # new request
        convert(_request.isBlockNum, bytes1),
        convert(_request.blockNumOrTimestamp, bytes8),
        convert(_request.confirmations, bytes2),
        convert(_request.to, bytes20),
        _request.callData,
    )


@internal
@pure
def appendEVMCallComputeV1(
    _cmd: Bytes[MAX_MESSAGE_SIZE], _compute: EVMCallComputeV1
) -> Bytes[MAX_MESSAGE_SIZE]:
    """
    @notice Appends an EVM call compute to the command
    @param _cmd The existing command bytes
    @param _compute The EVM call compute to append
    @return The updated command bytes
    """

    assert len(_cmd) + 39 <= MAX_MESSAGE_SIZE, "OApp: Command too large"
    # dev: 39 is length of all fields excluding existing command
    return concat(
        convert(_cmd, Bytes[MAX_MESSAGE_SIZE - 39]), # downcast Bytes size
        convert(COMPUTE_VERSION, bytes1),
        convert(COMPUTE_TYPE_SINGLE_VIEW_EVM_CALL, bytes2),
        convert(_compute.computeSetting, bytes1),
        convert(_compute.targetEid, bytes4),
        convert(_compute.isBlockNum, bytes1),
        convert(_compute.blockNumOrTimestamp, bytes8),
        convert(_compute.confirmations, bytes2),
        convert(_compute.to, bytes20),
    )
