# pragma version ~=0.4

"""
@title Layer Zero V2 Vyper Module

@notice Base contract for LayerZero cross-chain messaging. Provides core
functionality for lzSend messages and lzRead.

@dev Core functionality is organized around:
1. Option building - prepare_message_options and prepare_read_options for different message types
2. Read request preparation - prepare_read_message for encoding read requests from calldata
3. Unified sending - single _send_message function that works with both message types

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""

################################################################
#                         INTERFACES                           #
################################################################

interface ILayerZeroEndpointV2:
    def quote(_params: MessagingParams, _sender: address) -> MessagingFee: view
    def send(_params: MessagingParams, _refundAddress: address) -> (
        bytes32, uint64, uint256, uint256
    ): payable
    def setDelegate(_delegate: address): nonpayable
    def setSendLibrary(_oapp: address, _eid: uint32, _newLib: address): nonpayable
    def setReceiveLibrary(
        _oapp: address, _eid: uint32, _newLib: address, _gracePeriod: uint256
    ): nonpayable
    def setConfig(_oapp: address, _lib: address, _params: DynArray[SetConfigParam, 1]): nonpayable


################################################################
#                           CONSTANTS                          #
################################################################

# Message size limits
LZ_MESSAGE_SIZE_CAP: public(constant(uint256)) = 512
LZ_READ_CALLDATA_SIZE: public(constant(uint256)) = 256

# LayerZero protocol constants
TYPE_3: constant(bytes2) = 0x0003  # uint16
WORKER_ID: constant(bytes1) = 0x01  # uint8
OPTIONS_HEADER: constant(bytes3) = 0x000301  # concat(TYPE_3, WORKER_ID)

OPTION_TYPE_LZRECEIVE: constant(bytes1) = 0x01
OPTION_TYPE_NATIVE_DROP: constant(bytes1) = 0x02
OPTION_TYPE_LZREAD: constant(bytes1) = 0x05
READ_CHANNEL_THRESHOLD: constant(uint32) = 4294965694  # max(uint32)-1600

# Read codec constants
CMD_VERSION: constant(uint16) = 1
REQUEST_VERSION: constant(uint8) = 1
RESOLVER_TYPE: constant(uint16) = 1

# Options size cap
LZ_OPTION_SIZE: constant(uint256) = 64
LZ_DOUBLE_OPTION_SIZE: constant(uint256) = LZ_OPTION_SIZE * 2

################################################################
#                           STORAGE                            #
################################################################

LZ_ENDPOINT: public(immutable(address))
LZ_PEERS: public(HashMap[uint32, address])
LZ_READ_CHANNEL: public(uint32)
LZ_DELEGATE: public(address)
default_gas_limit: public(uint256)


################################################################
#                           STRUCTS                            #
################################################################

struct MessagingParams:
    dstEid: uint32
    receiver: bytes32  # Low level format for LZ
    message: Bytes[LZ_MESSAGE_SIZE_CAP]
    options: Bytes[LZ_OPTION_SIZE]
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


struct SetConfigParam:
    eid: uint32
    configType: uint32
    config: Bytes[1024]


struct ULNConfig:
    confirmations: uint64
    required_dvn_count: uint8
    optional_dvn_count: uint8
    optional_dvn_threshold: uint8
    required_dvns: DynArray[address, 10]  # Max 10 DVNs
    optional_dvns: DynArray[address, 10]  # Max 10 DVNs


struct ULNReadConfig:
    executor: address
    required_dvn_count: uint8
    optional_dvn_count: uint8
    optional_dvn_threshold: uint8
    required_dvns: DynArray[address, 10]  # Max 10 DVNs
    optional_dvns: DynArray[address, 10]  # Max 10 DVNs


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
#                   SETTERS [GUARD THESE!]                     #
################################################################
# Note: External wrappers to these internal functions must enforce
# proper authorization.
# Exposing these functions without ownership check will lead to anyone
# being able to bridge any message/command (=loss of funds).

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


@internal
def _set_delegate(_delegate: address):
    """@notice Set delegate that can change any LZ setting"""

    extcall ILayerZeroEndpointV2(LZ_ENDPOINT).setDelegate(_delegate)
    self.LZ_DELEGATE = _delegate


@internal
def _set_send_lib(_eid: uint32, _lib: address):
    """@notice Set new send library for send requests"""

    extcall ILayerZeroEndpointV2(LZ_ENDPOINT).setSendLibrary(self, _eid, _lib)


@internal
def _set_receive_lib(_eid: uint32, _lib: address):
    """@notice Set new receive library for receive requests"""

    extcall ILayerZeroEndpointV2(LZ_ENDPOINT).setReceiveLibrary(self, _eid, _lib, 0)
    # 0 is for grace period, not used in this contract


@internal
def _set_uln_config(
    _eid: uint32,
    _oapp: address,
    _lib: address,
    _config_type: uint32,
    _confirmations: uint64,
    _required_dvns: DynArray[address, 10],
    _optional_dvns: DynArray[address, 10],
    _optional_dvn_threshold: uint8,
):
    """
    @notice Set ULN config for remote endpoint
    @dev Arrays must be sorted in ascending order with no duplicates, or lz will fail
    """

    config_param: SetConfigParam = self._prepare_uln_config(
        _eid, _config_type, _confirmations, _required_dvns, _optional_dvns, _optional_dvn_threshold
    )

    # Call endpoint to set config
    extcall ILayerZeroEndpointV2(LZ_ENDPOINT).setConfig(_oapp, _lib, [config_param])


################################################################
#                      OPTION PREPARATION                      #
################################################################

@internal
@pure
def _prepare_message_options(_gas: uint256, _value: uint256) -> Bytes[LZ_OPTION_SIZE]:
    """
    @notice Build options for regular message sending
    @param _gas Gas limit for execution on destination
    """

    gas_option: bytes16 = convert(convert(_gas, uint128), bytes16)  # gas
    option_data: Bytes[32] = concat(gas_option, b'')  # explicitly create Bytes[32]

    if _value > 0:
        option_data = concat(gas_option, convert(convert(_value, uint128), bytes16))

    return concat(
        OPTIONS_HEADER,
        convert(convert(len(option_data) + 1, uint16), bytes2),  # length (option) + 1 [type]
        OPTION_TYPE_LZRECEIVE,
        option_data,
    )


@internal
@pure
def _prepare_read_options(
    _gas: uint256, _value: uint256, _data_size: uint32
) -> Bytes[LZ_OPTION_SIZE]:
    """
    @notice Build options for read request
    @param _gas Gas limit for execution
    @param _data_size Expected response data size
    @param _value Native value for execution
    """

    gas_data_option: Bytes[20] = concat(
        convert(convert(_gas, uint128), bytes16),  # gas
        convert(_data_size, bytes4),  # data size
    )
    option_data: Bytes[36] = concat(gas_data_option, b'')  # explicitly create Bytes[32]

    if _value > 0:
        option_data = concat(gas_data_option, convert(convert(_value, uint128), bytes16))

    return concat(
        OPTIONS_HEADER,
        convert(convert(len(option_data) + 1, uint16), bytes2),  # length (option) + 1 [type]
        OPTION_TYPE_LZREAD,
        option_data,
    )


@internal
@pure
def _prepare_uln_config(
    _eid: uint32,
    _config_type: uint32,
    _confirmations: uint64,
    _required_dvns: DynArray[address, 10],
    _optional_dvns: DynArray[address, 10],
    _optional_dvn_threshold: uint8,
) -> SetConfigParam:
    """
    @notice Prepare ULN config from arrays, automatically calculating counts
    """

    required_count: uint8 = convert(len(_required_dvns), uint8)
    optional_count: uint8 = convert(len(_optional_dvns), uint8)

    assert _optional_dvn_threshold <= optional_count, "Invalid DVN threshold"

    if _eid > READ_CHANNEL_THRESHOLD:  # read config
        uln_config: ULNReadConfig = ULNReadConfig(
            executor=empty(address),  # default executor
            required_dvn_count=required_count,
            optional_dvn_count=optional_count,
            optional_dvn_threshold=_optional_dvn_threshold,
            required_dvns=_required_dvns,
            optional_dvns=_optional_dvns,
        )
        return SetConfigParam(eid=_eid, configType=_config_type, config=abi_encode(uln_config))
    else:
        uln_config: ULNConfig = ULNConfig(
            confirmations=_confirmations,
            required_dvn_count=required_count,
            optional_dvn_count=optional_count,
            optional_dvn_threshold=_optional_dvn_threshold,
            required_dvns=_required_dvns,
            optional_dvns=_optional_dvns,
        )
        return SetConfigParam(eid=_eid, configType=_config_type, config=abi_encode(uln_config))


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
    _value: uint256 = 0,
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
    options: Bytes[LZ_OPTION_SIZE] = (
        self._prepare_read_options(gas, _value, _data_size)
        if _data_size > 0
        else self._prepare_message_options(gas, _value)
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
    _value: uint256 = 0,
    _data_size: uint32 = 0,
) -> uint256:
    """@notice Quote fee using prepared parameters"""

    params: MessagingParams = self._prepare_messaging_params(
        _dstEid, convert(_receiver, bytes32), _message, _gas_limit, _value, _data_size
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
    _value: uint256 = 0,
    _data_size: uint32 = 0,
    _perform_fee_check: bool = False,
):
    """@notice Send message using prepared parameters"""

    params: MessagingParams = self._prepare_messaging_params(
        _dstEid, _receiver, _message, _gas_limit, _value, _data_size
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
    assert self.LZ_PEERS[_origin.srcEid] != empty(address), "LZ Peer not set"
    assert (
        convert(_origin.sender, address) == self.LZ_PEERS[_origin.srcEid]
    ), "Invalid LZ message source!"
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
    """
    @notice Prepare read request message from basic parameters
    @dev Constructs EVMCallRequestV1, encodes it into message and returns Bytes
    Uses current block timestamp and default confirmations.
    """

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
    _value: uint256 = 0,
    _data_size: uint32 = 0,
) -> uint256:
    """@notice Quote fee for sending message"""

    return self._quote_lz_fee(_dstEid, _receiver, _message, _gas_limit, _value, _data_size)


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
