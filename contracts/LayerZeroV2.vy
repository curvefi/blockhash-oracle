# pragma version ~=0.4

"""
@title Layer Zero V2 Vyper Module

@notice Base contract for LayerZero cross-chain messaging. Provides core
functionality for lzSend messages and lzRead.

@dev Core functionality is organized around:
1. Option building - prepare_message_options and prepare_read_options for different message types
2. Read request preparation - prepare_read_message for encoding read requests from calldata
3. Unified sending - single _send_message function that works with both message types

@license Copyright (c) Curve.Fi, 2020-2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""

################################################################
#                           CONSTANTS                          #
################################################################

# Message size limits
LZ_MESSAGE_SIZE_CAP: public(constant(uint256)) = 512
LZ_READ_CALLDATA_SIZE: public(constant(uint256)) = 256

# LayerZero protocol constants
TYPE_3: constant(bytes2) = 0x0003
WORKER_ID: constant(bytes1) = 0x01
OPTION_TYPE_LZRECEIVE: constant(bytes1) = 0x01
OPTION_TYPE_LZREAD: constant(bytes1) = 0x05
READ_CHANNEL_THRESHOLD: constant(uint32) = 4294965694  # max(uint32)-1600

# Read codec constants
CMD_VERSION: constant(uint16) = 1
REQUEST_VERSION: constant(uint8) = 1
RESOLVER_TYPE: constant(uint16) = 1


################################################################
#                           STRUCTS                            #
################################################################

struct MessagingParams:
    dstEid: uint32
    receiver: bytes32  # Low level format for LZ
    message: Bytes[LZ_MESSAGE_SIZE_CAP]
    options: Bytes[64]
    payInLzToken: bool


struct MessagingFee:
    nativeFee: uint256
    lzTokenFee: uint256


struct Origin:
    srcEid: uint32
    sender: bytes32
    nonce: uint64


struct EVMCallRequestV1:
    appRequestLabel: uint16
    targetEid: uint32
    isBlockNum: bool
    blockNumOrTimestamp: uint64
    confirmations: uint16
    to: address
    callData: Bytes[LZ_READ_CALLDATA_SIZE]


################################################################
#                         INTERFACES                           #
################################################################

interface ILayerZeroEndpointV2:
    def quote(_params: MessagingParams, _sender: address) -> MessagingFee: view
    def send(_params: MessagingParams, _refundAddress: address) -> (
        bytes32, uint64, uint256, uint256
    ): payable


################################################################
#                           STORAGE                            #
################################################################

LZ_ENDPOINT: public(immutable(address))
LZ_PEERS: public(HashMap[uint32, address])
LZ_READ_CHANNEL: public(uint32)
default_gas_limit: public(uint256)


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__(_endpoint: address, _gas_limit: uint256, _read_channel: uint32):
    """@notice Initialize with endpoint and default gas limit"""
    LZ_ENDPOINT = _endpoint
    self._set_default_gas_limit(_gas_limit)
    self._set_lz_read_channel(_read_channel)


################################################################
#                           SETTERS                            #
################################################################

@internal
def _set_peer(_srcEid: uint32, _peer: address):
    """@notice Set trusted peer for chain ID"""
    self.LZ_PEERS[_srcEid] = _peer


@internal
def _set_default_gas_limit(_gas_limit: uint256):
    """@notice Update default gas limit"""
    self.default_gas_limit = _gas_limit


@internal
def _set_lz_read_channel(_read_channel: uint32):
    """@notice Set read channel ID"""
    self.LZ_READ_CHANNEL = _read_channel


################################################################
#                      OPTION PREPARATION                      #
################################################################

@internal
@pure
def _prepare_message_options(_gas: uint256) -> Bytes[64]:
    """
    @notice Build options for regular message sending
    @param _gas Gas limit for execution on destination
    """
    return concat(
        TYPE_3,
        WORKER_ID,
        convert(17, bytes2),
        OPTION_TYPE_LZRECEIVE,
        convert(convert(_gas, uint128), bytes16),
    )


@internal
@pure
def _prepare_read_options(_gas: uint256, _data_size: uint32) -> Bytes[64]:
    """
    @notice Build options for read request
    @param _gas Gas limit for execution
    @param _data_size Expected response data size
    """
    return concat(
        TYPE_3,
        WORKER_ID,
        convert(21, bytes2),  # length (16 + 4 + 1)
        OPTION_TYPE_LZREAD,
        convert(convert(_gas, uint128), bytes16),  # gas
        convert(_data_size, bytes4),  # data size
    )


################################################################
#                    READ MESSAGE ENCODING                     #
################################################################

@view
@internal
def _is_read_response(_origin: Origin) -> bool:
    return _origin.srcEid > READ_CHANNEL_THRESHOLD


@internal
@pure
def _encode_read_request(_request: EVMCallRequestV1) -> Bytes[LZ_MESSAGE_SIZE_CAP]:
    """
    @notice Encode read request following ReadCmdCodecV1 format
    @param _request The read request to encode
    """
    # Calculate request size (35 bytes of fixed fields + calldata)
    request_size: uint16 = convert(len(_request.callData) + 35, uint16)

    # First part of headers (matches ReadCmdCodecV1.sol:183)
    encoded_headers_1: Bytes[6] = concat(
        convert(CMD_VERSION, bytes2),  # version = 1
        convert(0, bytes2),  # appCmdLabel = 0
        convert(1, bytes2),  # requests length = 1
    )

    # Complete headers (matches ReadCmdCodecV1.sol:195)
    encoded_headers_2: Bytes[13] = concat(
        encoded_headers_1,  # 6 bytes
        convert(REQUEST_VERSION, bytes1),  # version = 1
        convert(_request.appRequestLabel, bytes2),  # request label
        convert(RESOLVER_TYPE, bytes2),  # resolver type = 1
        convert(request_size, bytes2),  # payload size
    )

    # Add request fields (matches ReadCmdCodecV1.sol:204)
    return concat(
        encoded_headers_2,  # 13 bytes
        convert(_request.targetEid, bytes4),  # +4=17
        convert(_request.isBlockNum, bytes1),  # +1=18
        convert(_request.blockNumOrTimestamp, bytes8),  # +8=26
        convert(_request.confirmations, bytes2),  # +2=28
        convert(_request.to, bytes20),  # +20=48 (35 w/o headers)
        _request.callData,  # +variable
    )


################################################################
#                       CORE FUNCTIONS                         #
################################################################
@internal
@view
def _prepare_messaging_params(
    _dstEid: uint32,
    _receiver: bytes32,
    _message: Bytes[LZ_MESSAGE_SIZE_CAP],
    _gas_limit: uint256,
    _data_size: uint32 = 0,  # Zero indicates regular message, non-zero for read
) -> MessagingParams:
    """
    @notice Prepare parameters for LayerZero endpoint interactions
    @dev This function unifies parameter preparation for both sending and quoting.
    The same structure is needed in both cases since they interact with the same
    endpoint interface. The data_size parameter determines if we're preparing
    for a regular message (data_size=0) or a read request (data_size>0).

    @param _dstEid Destination chain ID
    @param _receiver Target address (empty for reads)
    @param _message Message payload or encoded read request
    @param _gas_limit Gas limit for execution
    @param _data_size For read requests, expected response size
    @return Prepared parameters for endpoint interaction
    """
    gas: uint256 = _gas_limit if _gas_limit != 0 else self.default_gas_limit

    # Choose appropriate options based on message type
    options: Bytes[64] = (
        self._prepare_read_options(gas, _data_size)
        if _data_size > 0
        else self._prepare_message_options(gas)
    )

    return MessagingParams(
        dstEid=_dstEid, receiver=_receiver, message=_message, options=options, payInLzToken=False
    )


@view
@internal
def _prepare_read_message_bytes(
    _dst_eid: uint32,
    _target: address,
    _calldata: Bytes[LZ_READ_CALLDATA_SIZE],
    _isBlockNum: bool = False,  # Use timestamp by default
    _blockNumOrTimestamp: uint64 = 0,  # Uses latest ts (or block!) if 0
    _confirmations: uint16 = 15,
) -> Bytes[LZ_MESSAGE_SIZE_CAP]:
    """
    @notice Helper to prepare read request message from basic parameters
    @dev Constructs EVMCallRequestV1, encodes it into message and returns
    all parameters needed for quote or send. Uses current block timestamp
    and default confirmations.

    @param _dst_eid Target chain ID to read from
    @param _target Contract address to read from
    @param _calldata Function call data
    @return Parameters for quoting/sending:
        - destination chain ID (will be READ_CHANNEL)
        - receiver (empty for reads)
        - encoded message
    """
    # Process block number or timestamp
    blockNumOrTimestamp: uint64 = _blockNumOrTimestamp
    if blockNumOrTimestamp == 0:
        if _isBlockNum:
            blockNumOrTimestamp = convert(block.number, uint64)
        else:
            blockNumOrTimestamp = convert(block.timestamp, uint64)

    # Create read request with sensible defaults
    request: EVMCallRequestV1 = EVMCallRequestV1(
        appRequestLabel=1,
        targetEid=_dst_eid,
        isBlockNum=_isBlockNum,
        blockNumOrTimestamp=blockNumOrTimestamp,
        confirmations=_confirmations,  # Default confirmations
        to=_target,
        callData=_calldata,
    )

    # Encode request into message
    message: Bytes[LZ_MESSAGE_SIZE_CAP] = self._encode_read_request(request)

    return message


@view
@internal
def _quote_lz_fee(
    _dstEid: uint32,
    _receiver: address,
    _message: Bytes[LZ_MESSAGE_SIZE_CAP],
    _gas_limit: uint256 = 0,
    _data_size: uint32 = 0,
) -> uint256:
    """@notice Quote fee using prepared parameters"""
    params: MessagingParams = self._prepare_messaging_params(
        _dstEid, convert(_receiver, bytes32), _message, _gas_limit, _data_size
    )
    fees: MessagingFee = staticcall ILayerZeroEndpointV2(LZ_ENDPOINT).quote(params, self)
    return fees.nativeFee


@payable
@internal
def _send_message(
    _dstEid: uint32,
    _receiver: bytes32,
    _message: Bytes[LZ_MESSAGE_SIZE_CAP],
    _gas_limit: uint256 = 0,
    _data_size: uint32 = 0,
    _perform_fee_check: bool = False,
):
    """@notice Send message using prepared parameters"""
    params: MessagingParams = self._prepare_messaging_params(
        _dstEid, _receiver, _message, _gas_limit, _data_size
    )

    if _perform_fee_check:
        fees: MessagingFee = staticcall ILayerZeroEndpointV2(LZ_ENDPOINT).quote(params, self)
        assert msg.value >= fees.nativeFee, "Not enough fees"

    extcall ILayerZeroEndpointV2(LZ_ENDPOINT).send(params, msg.sender, value=msg.value)


@payable
@internal
def _lz_receive(
    _origin: Origin,
    _guid: bytes32,
    _message: Bytes[LZ_MESSAGE_SIZE_CAP],
    _executor: address,
    _extraData: Bytes[64],
) -> bool:
    """
    @notice Base security checks for received messages
    @dev Must be called by importing contract's lzReceive
    """
    assert msg.sender == LZ_ENDPOINT, "Not LZ endpoint"
    assert self.LZ_PEERS[_origin.srcEid] != empty(address), "Peer not set"
    assert convert(_origin.sender, address) == self.LZ_PEERS[_origin.srcEid], "Invalid peer"
    return True


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################
@view
@external
def prepare_read_message_bytes(
    _dst_eid: uint32,
    _target: address,
    _calldata: Bytes[LZ_READ_CALLDATA_SIZE],
    _isBlockNum: bool = False,  # Use timestamp by default
    _blockNumOrTimestamp: uint64 = 0,  # Uses latest ts (or block!) if 0
    _confirmations: uint16 = 15,
) -> Bytes[LZ_MESSAGE_SIZE_CAP]:
    return self._prepare_read_message_bytes(
        _dst_eid, _target, _calldata, _isBlockNum, _blockNumOrTimestamp, _confirmations
    )


@view
@external
def quote_lz_fee(
    _dstEid: uint32,
    _receiver: address,
    _message: Bytes[LZ_MESSAGE_SIZE_CAP],
    _gas_limit: uint256 = 0,
    _data_size: uint32 = 0,
) -> uint256:
    return self._quote_lz_fee(_dstEid, _receiver, _message, _gas_limit, _data_size)

@view
@external
def nextNonce(_srcEid: uint32, _sender: bytes32) -> uint64:
    """@notice Protocol endpoint for nonce tracking"""
    return 0


@view
@external
def allowInitializePath(_origin: Origin) -> bool:
    """@notice Protocol endpoint for path initialization"""
    return True
