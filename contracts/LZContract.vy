# @version ^0.4.0
"""
@title Minimal LayerZero V2 Sender
@notice Simple contract to test LZ sending on Base Sepolia
"""

struct MessagingParams:
    dstEid: uint32
    receiver: bytes32
    message: Bytes[64]
    options: Bytes[64]
    payInLzToken: bool

struct MessagingFee:
    nativeFee: uint256
    lzTokenFee: uint256

interface ILayerZeroEndpointV2:
    def quote(
        _params: MessagingParams,
        _sender: address
    ) -> MessagingFee: view

    def send(
        _params: MessagingParams,
        _refundAddress: address
    ) -> (bytes32, uint64, uint256, uint256): payable

event MessageSent:
    dstEid: uint32
    timestamp: uint256
    fees: uint256

# Constants for options building
TYPE_3: constant(bytes2) = 0x0003
WORKER_ID: constant(bytes1) = 0x01
OPTION_TYPE_LZRECEIVE: constant(bytes1) = 0x01
OPTION_TYPE_LZREAD: constant(bytes1) = 0x05

ENDPOINT: public(immutable(address))

@internal
@pure
def _build_lz_receive_option(_gas: uint256) -> Bytes[32]:
    """
    @notice Build basic LZ receive option with gas limit
    @param _gas Gas limit for destination execution
    """
    return concat(
        TYPE_3,
        WORKER_ID,
        convert(17, bytes2),  # length (16 + 1 for type)
        OPTION_TYPE_LZRECEIVE,
        convert(convert(_gas, uint128), bytes16)  # gas amount padded to 128 bits
    )


@internal
@pure
def _build_lz_read_option(_gas: uint256, _data_size: uint32) -> Bytes[32]:
    """
    @notice Build option for LZ Read operations
    @param _gas Gas limit
    @param _data_size Expected response data size
    """
    return concat(
        TYPE_3,
        WORKER_ID,
        convert(21, bytes2),  # length (16 + 4 + 1 for type)
        OPTION_TYPE_LZREAD,
        convert(convert(_gas, uint128), bytes16),  # gas amount padded to 128 bits
        convert(_data_size, bytes4)  # data size as uint32
    )

@deploy
def __init__(_endpoint: address):
    ENDPOINT = _endpoint

@payable
@external
def send_message(_dstEid: uint32, _receiver: address, _gas_limit: uint256 = 60000):
    """
    @notice Send message with default receive gas
    """
    peer: bytes32 = convert(convert(_receiver, bytes20), bytes32)
    payload: Bytes[64] = abi_encode(block.timestamp)

    # Basic receive option with 60k gas
    options: Bytes[64] = self._build_lz_receive_option(_gas_limit)

    params: MessagingParams = MessagingParams(
        dstEid = _dstEid,
        receiver = peer,
        message = payload,
        options = options,
        payInLzToken = False
    )

    fees: MessagingFee = staticcall ILayerZeroEndpointV2(ENDPOINT).quote(params, self)
    assert msg.value == fees.nativeFee, "Invalid fee amount"
    assert fees.lzTokenFee == 0, "LZ token fee not supported"

    extcall ILayerZeroEndpointV2(ENDPOINT).send(
        params,
        msg.sender,
        value=fees.nativeFee
    )

    log MessageSent(_dstEid, block.timestamp, fees.nativeFee)

@view
@external
def quote_fee(_dstEid: uint32, _receiver: address, _gas_limit: uint256 = 60000) -> uint256:
    """
    @notice Quote fee for simple message
    """
    peer: bytes32 = convert(convert(_receiver, bytes20), bytes32)
    payload: Bytes[64] = abi_encode(block.timestamp)
    options: Bytes[64] = self._build_lz_receive_option(_gas_limit)

    params: MessagingParams = MessagingParams(
        dstEid = _dstEid,
        receiver = peer,
        message = payload,
        options = options,
        payInLzToken = False
    )
    fees: MessagingFee = staticcall ILayerZeroEndpointV2(ENDPOINT).quote(params, self)
    return fees.nativeFee
