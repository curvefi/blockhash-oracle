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
    def send(_params: MessagingParams, _refundAddress: address) -> MessagingReceipt: payable
    def setDelegate(_delegate: address): nonpayable
    def setSendLibrary(_oapp: address, _eid: uint32, _newLib: address): nonpayable
    def setReceiveLibrary(
        _oapp: address, _eid: uint32, _newLib: address, _gracePeriod: uint256
    ): nonpayable
    def setConfig(_oapp: address, _lib: address, _params: DynArray[SetConfigParam, 1]): nonpayable
    def eid() -> uint32: view


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
READ_CHANNEL_THRESHOLD: constant(uint32) = 4294965694  # max(uint32)-1601, 1600 channels reserved for read

# Read codec constants
CMD_VERSION: constant(uint16) = 1
REQUEST_VERSION: constant(uint8) = 1
RESOLVER_TYPE: constant(uint16) = 1

# Options size cap
LZ_OPTION_SIZE: constant(uint256) = 64

#
MAX_DVNS: constant(uint8) = 10
MAX_PEERS: constant(uint256) = 128


################################################################
#                           STORAGE                            #
################################################################

LZ_ENDPOINT: public(ILayerZeroEndpointV2)  # Not immutable for init fcn
EID: public(uint32)
LZ_PEERS: public(HashMap[uint32, address])
LZ_READ_CHANNEL: public(uint32)
LZ_DELEGATE: public(address)
default_gas_limit: public(uint256)
is_initialized: public(bool)

# Track configured peer EIDs
configured_eids: DynArray[uint32, MAX_PEERS]


################################################################
#                           STRUCTS                            #
################################################################

struct MessagingParams:
    dstEid: uint32
    receiver: bytes32  # Low level format for LZ
    message: Bytes[LZ_MESSAGE_SIZE_CAP]
    options: Bytes[LZ_OPTION_SIZE]
    payInLzToken: bool


struct MessagingReceipt:
    guid: bytes32
    nonce: uint64
    fee: MessagingFee


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
    required_dvns: DynArray[address, MAX_DVNS]  # Max 10 DVNs
    optional_dvns: DynArray[address, MAX_DVNS]  # Max 10 DVNs


struct ULNReadConfig:
    executor: address
    required_dvn_count: uint8
    optional_dvn_count: uint8
    optional_dvn_threshold: uint8
    required_dvns: DynArray[address, MAX_DVNS]  # Max 10 DVNs
    optional_dvns: DynArray[address, MAX_DVNS]  # Max 10 DVNs


struct ULNExecutorConfig:
    max_message_size: uint32
    executor: address


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__():
    """
    @notice Empty constructor for deterministic deployment
    """
    pass


################################################################
#                   SETTERS [GUARD THESE!]                     #
################################################################
# Note: External wrappers to these internal functions must enforce
# proper authorization.
# Exposing these functions without ownership check will lead to anyone
# being able to bridge any message/command (=loss of funds).

@internal
def _initialize(
    _endpoint: address,
    _default_gas_limit: uint256,
    _read_channel: uint32,
    _peer_eids: DynArray[uint32, MAX_PEERS],
    _peers: DynArray[address, MAX_PEERS],
):
    """
    @notice Configure the contract with core settings
    @param _endpoint LayerZero endpoint address
    @param _default_gas_limit Default gas limit for messages
    @param _read_channel LZ Read channel ID
    @dev can only be called once
    """
    assert _endpoint != empty(address), "Invalid endpoint"
    assert len(_peer_eids) == len(_peers), "Invalid peer arrays"
    assert not self.is_initialized, "Already initialized"

    self.LZ_ENDPOINT = ILayerZeroEndpointV2(_endpoint)
    self.EID = staticcall self.LZ_ENDPOINT.eid()
    self._set_default_gas_limit(_default_gas_limit)
    self._set_lz_read_channel(_read_channel)
    for i: uint256 in range(0, len(_peer_eids), bound=MAX_PEERS):
        self._set_peer(_peer_eids[i], _peers[i])
    self.is_initialized = True


@internal
def _set_peer(_srcEid: uint32, _peer: address):
    """@notice Set trusted peer for chain ID"""

    old_peer: address = self.LZ_PEERS[_srcEid]
    self.LZ_PEERS[_srcEid] = _peer

    # Update configured_eids list
    if old_peer == empty(address) and _peer != empty(address):
        # New peer being added
        self.configured_eids.append(_srcEid)
    elif old_peer != empty(address) and _peer == empty(address):
        # Peer being removed
        updated_eids: DynArray[uint32, MAX_PEERS] = []
        for eid: uint32 in self.configured_eids:
            if eid != _srcEid:
                updated_eids.append(eid)
        self.configured_eids = updated_eids


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

    extcall self.LZ_ENDPOINT.setDelegate(_delegate)
    self.LZ_DELEGATE = _delegate


@internal
def _set_send_lib(_eid: uint32, _lib: address):
    """@notice Set new send library for send requests"""

    extcall self.LZ_ENDPOINT.setSendLibrary(self, _eid, _lib)


@internal
def _set_receive_lib(_eid: uint32, _lib: address, _grace_period: uint256 = 0):
    """@notice Set new receive library for receive requests"""

    extcall self.LZ_ENDPOINT.setReceiveLibrary(self, _eid, _lib, _grace_period)


@internal
def _set_uln_config(
    _eid: uint32,
    _lib: address,
    _config_type: uint32,
    _confirmations: uint64,
    _required_dvns: DynArray[address, MAX_DVNS],
    _optional_dvns: DynArray[address, MAX_DVNS],
    _optional_dvn_threshold: uint8,
    _executor: address = empty(address),
):
    """
    @notice Set ULN config for remote endpoint
    @dev Arrays must be sorted in ascending order with no duplicates, or lz will fail
    """

    config_param: SetConfigParam = self._prepare_uln_config(
        _eid,
        _config_type,
        _confirmations,
        _required_dvns,
        _optional_dvns,
        _optional_dvn_threshold,
        _executor,
    )

    # Call endpoint to set config
    extcall self.LZ_ENDPOINT.setConfig(self, _lib, [config_param])

    if _executor != empty(address) and _eid <= READ_CHANNEL_THRESHOLD:
        # Set executor for ULN config
        executor_config: ULNExecutorConfig = ULNExecutorConfig(
            max_message_size=1024,
            executor=_executor,
        )
        config_param_executor: SetConfigParam = SetConfigParam(
            eid=_eid,
            configType=1,  # 1 = ULN executor config
            config=abi_encode(executor_config),
        )
        extcall self.LZ_ENDPOINT.setConfig(self, _lib, [config_param_executor])


################################################################
#                      OPTION PREPARATION                      #
################################################################

@internal
@pure
def _prepare_options(_gas: uint256, _value: uint256, _data_size: uint32) -> Bytes[LZ_OPTION_SIZE]:
    """
    @notice Build options for message sending
    @param _gas Gas limit for execution on destination
    @param _value Optional native value
    @param _data_size If nonzero, indicates a read request; otherwise regular message
    """
    gas_bytes: bytes16 = convert(convert(_gas, uint128), bytes16)  # gas
    value_bytes: bytes16 = convert(convert(_value, uint128), bytes16)  # value
    data_size_bytes: bytes4 = convert(_data_size, bytes4)  # data size

    full_option: Bytes[36] = empty(Bytes[36])
    if _data_size > 0 and _value > 0:
        # read request with value
        full_option = concat(gas_bytes, data_size_bytes, value_bytes)
    elif _data_size > 0:
        # read request without value
        full_option = concat(gas_bytes, data_size_bytes)
    elif _value > 0:
        # regular message with value
        full_option = concat(gas_bytes, value_bytes)
    else:
        # regular message without value
        full_option = concat(gas_bytes, b"") # bytes -> Bytes

    return concat(
        OPTIONS_HEADER,
        convert(convert(len(full_option) + 1, uint16), bytes2),  # length (option) + 1 [type]
        OPTION_TYPE_LZREAD if _data_size > 0 else OPTION_TYPE_LZRECEIVE,
        full_option,
    )


@internal
@pure
def _prepare_uln_config(
    _eid: uint32,
    _config_type: uint32,
    _confirmations: uint64,
    _required_dvns: DynArray[address, MAX_DVNS],
    _optional_dvns: DynArray[address, MAX_DVNS],
    _optional_dvn_threshold: uint8,
    _executor: address = empty(address),
) -> SetConfigParam:
    """
    @notice Prepare ULN config from arrays, automatically calculating counts
    """

    required_count: uint8 = convert(len(_required_dvns), uint8)
    optional_count: uint8 = convert(len(_optional_dvns), uint8)

    assert _optional_dvn_threshold <= optional_count, "Invalid DVN threshold"

    if _eid > READ_CHANNEL_THRESHOLD:  # read config
        uln_config: ULNReadConfig = ULNReadConfig(
            executor=_executor,
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
    options: Bytes[LZ_OPTION_SIZE] = self._prepare_options(gas, _value, _data_size)
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
    fees: MessagingFee = staticcall self.LZ_ENDPOINT.quote(params, self)
    return fees.nativeFee


@payable
@internal
def _send_message(
    _dstEid: uint32,
    _receiver: bytes32,
    _message: Bytes[LZ_MESSAGE_SIZE_CAP],
    _gas_limit: uint256 = 0,
    _lz_receive_value: uint256 = 0,
    _data_size: uint32 = 0,
    _request_msg_value: uint256 = 0,
    _refund_address: address = msg.sender,
    _perform_fee_check: bool = False,
) -> MessagingReceipt:
    """@notice Send message using prepared parameters
    @dev This function is used to send both regular messages and read requests
    @param _dstEid Destination chain ID
    @param _receiver Target address
    @param _message Message payload or encoded read request
    @param _gas_limit Gas limit for execution
    @param _lz_receive_value Value to send in lzReceive
    @param _data_size For read requests, expected response size
    @param _request_msg_value Value to send in request message (msg.value or less)
    @param _refund_address Address to refund any excess msg.value
    @param _perform_fee_check Whether to perform fee check
    """

    params: MessagingParams = self._prepare_messaging_params(
        _dstEid, _receiver, _message, _gas_limit, _lz_receive_value, _data_size
    )

    # optional logic to call send as part of larger transaction
    message_value: uint256 = 0
    if _request_msg_value == 0:
        message_value = msg.value
    else:
        message_value = _request_msg_value

    if _perform_fee_check:
        fees: MessagingFee = staticcall self.LZ_ENDPOINT.quote(params, self)
        assert message_value >= fees.nativeFee, "Not enough fees"

    return extcall self.LZ_ENDPOINT.send(params, _refund_address, value=message_value)


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
    peer: address = self.LZ_PEERS[_origin.srcEid]
    assert msg.sender == self.LZ_ENDPOINT.address, "Not LZ endpoint"
    assert peer != empty(address), "LZ Peer not set"
    assert convert(_origin.sender, address) == peer, "Invalid LZ message source!"
    return True


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@view
@external
def get_configured_eids() -> DynArray[uint32, MAX_PEERS]:
    """
    @notice Get list of all configured peer EIDs
    @return List of EIDs that have non-zero peer addresses
    """
    return self.configured_eids


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
