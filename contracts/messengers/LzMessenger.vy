# pragma version ~=0.4

"""
@title Example LayerZero Messenger

@notice Example implementation of LZ Base module for simple messaging between
chains. Allows sending and receiving string messages across chains using LayerZero
protocol. Includes ownership control for secure peer management and configuration.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""

################################################################
#                           INTERFACES                         #
################################################################

# Import LayerZero module for cross-chain messaging
import LayerZeroV2 as lz
initializes: lz
exports: (
    lz.LZ_ENDPOINT,
    lz.LZ_PEERS,
    lz.LZ_DELEGATE,
    lz.LZ_MESSAGE_SIZE_CAP,
    lz.LZ_READ_CALLDATA_SIZE,
    lz.LZ_READ_CHANNEL,
    lz.default_gas_limit,
    lz.quote_lz_fee,
    lz.nextNonce,
    lz.allowInitializePath,
)

# Import ownership management
from snekmate.auth import ownable
from snekmate.auth import ownable_2step

initializes: ownable
initializes: ownable_2step[ownable := ownable]
exports: (
    ownable_2step.owner,
    ownable_2step.pending_owner,
    ownable_2step.transfer_ownership,
    ownable_2step.accept_ownership,
    ownable_2step.renounce_ownership,
)

################################################################
#                            EVENTS                            #
################################################################

event MessageSent:
    destination: uint32
    payload: String[128]
    fees: uint256


event MessageReceived:
    source: uint32
    payload: String[128]


event ReadRequestSent:
    destination: uint32
    target: address
    payload: Bytes[128]


event ReadResponseReceived:
    source: uint32
    response: String[128]


################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__(_endpoint: address, _gas_limit: uint256):
    """
    @notice Initialize messenger with LZ endpoint and default gas settings
    @param _endpoint LayerZero endpoint address
    @param _gas_limit Default gas limit for cross-chain messages
    """
    lz.__init__(_endpoint, _gas_limit, 4294967295)
    lz._set_delegate(msg.sender)
    ownable.__init__()
    ownable_2step.__init__()


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def set_peer(_srcEid: uint32, _peer: address):
    """
    @notice Set trusted peer contract on another chain
    @param _srcEid Target endpoint ID
    @param _peer Contract address on target chain
    """

    ownable._check_owner()
    lz._set_peer(_srcEid, _peer)


@external
def set_default_gas(_gas_limit: uint256):
    """
    @notice Update default gas limit for messages
    @param _gas_limit New gas limit
    """

    ownable._check_owner()
    lz._set_default_gas_limit(_gas_limit)


@external
def set_lz_read_channel(_new_channel: uint32):
    """
    @notice Set new read channel for read requests
    @param _new_channel New read channel ID
    """

    ownable._check_owner()
    lz._set_lz_read_channel(_new_channel)


@external
def set_lz_send_lib(_channel: uint32, _lib: address):
    """
    @notice Set new send library for send requests
    @param _channel Send channel ID
    @param _lib New send library address
    """

    ownable._check_owner()
    lz._set_send_lib(_channel, _lib)


@external
def set_lz_receive_lib(_channel: uint32, _lib: address):
    """
    @notice Set new receive library for receive requests
    @param _channel Receive channel ID
    @param _lib New receive library address
    """

    ownable._check_owner()
    lz._set_receive_lib(_channel, _lib)


@external
def set_lz_delegate(_delegate: address):
    """
    @notice Set new delegate for LayerZero operations
    @param _delegate New delegate address
    """

    ownable._check_owner()
    lz._set_delegate(_delegate)


@external
def set_lz_uln_config(
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
    @notice Set new ULN configuration for cross-chain messages
    @param _eid Endpoint ID
    @param _oapp Originating application address
    @param _lib Library address
    @param _config_type Configuration type
    @param _confirmations Number of confirmations required
    @param _required_dvns List of required DVN addresses
    @param _optional_dvns List of optional DVN addresses
    @param _optional_dvn_threshold Optional DVN threshold
    """

    ownable._check_owner()
    lz._set_uln_config(
        _eid,
        _oapp,
        _lib,
        _config_type,
        _confirmations,
        _required_dvns,
        _optional_dvns,
        _optional_dvn_threshold,
    )


@external
def withdraw_eth(_amount: uint256):
    """
    @notice Withdraw ETH from contract
    @param _amount Amount to withdraw
    """

    ownable._check_owner()
    assert self.balance >= _amount, "Insufficient balance"
    send(msg.sender, _amount)


################################################################
#                    MESSAGING FUNCTIONS                       #
################################################################

@view
@external
def quote_message_fee(
    _dst_eid: uint32,
    _receiver: address,
    _message: String[128],
    _gas_limit: uint256 = 0,
    _value: uint256 = 0,
) -> uint256:
    """
    @notice Quote fee for sending message
    """

    encoded: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = convert(_message, Bytes[lz.LZ_MESSAGE_SIZE_CAP])
    return lz._quote_lz_fee(_dst_eid, _receiver, encoded, _gas_limit, _value)


@payable
@external
def send_message(
    _dst_eid: uint32,
    _receiver: address,
    _message: String[128],
    _gas_limit: uint256 = 0,
    _value: uint256 = 0,
    _check_fee: bool = False,
):
    """
    @notice Send a string message to contract on another chain
    @param _dst_eid Destination chain ID
    @param _receiver Target contract address
    @param _message String message to send
    @param _gas_limit Optional gas limit override
    @param _value Optional value to send with message
    """

    encoded: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = convert(_message, Bytes[lz.LZ_MESSAGE_SIZE_CAP])
    lz._send_message(
        _dst_eid, convert(_receiver, bytes32), encoded, _gas_limit, _value, 0, _check_fee
    )
    log MessageSent(_dst_eid, _message, msg.value)


@view
@external
def quote_read_fee(
    _dst_eid: uint32,
    _target: address,
    _calldata: Bytes[128],
    _gas_limit: uint256 = 0,
    _value: uint256 = 0,
    _data_size: uint32 = 64,
) -> uint256:
    """
    @notice Quote fee for read request
    """

    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = lz._prepare_read_message_bytes(
        _dst_eid, _target, _calldata
    )

    return lz._quote_lz_fee(
        lz.LZ_READ_CHANNEL, empty(address), message, _gas_limit, _value, _data_size
    )


@payable
@external
def request_read(
    _dst_eid: uint32,
    _target: address,
    _calldata: Bytes[128],
    _gas_limit: uint256 = 0,
    _value: uint256 = 0,
    _data_size: uint32 = 64,
    _check_fee: bool = False,
):
    """
    @notice Send read request to another chain
    @param _dst_eid Target chain endpoint ID
    @param _target Contract to read from
    @param _calldata Function call data
    @param _gas_limit Optional gas limit
    @param _value Optional value to send with message
    @param _data_size Expected response size
    @param _check_fee Validate sufficent fee before sending
    """

    # Prepare read message
    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = lz._prepare_read_message_bytes(
        _dst_eid, _target, _calldata, False, convert(block.timestamp, uint64), 1
    )

    # Send to read channel
    lz._send_message(
        lz.LZ_READ_CHANNEL,  # Read channel
        convert(self, bytes32),  # self receiver for reads
        message,
        _gas_limit,
        _value,
        _data_size,
        _check_fee,
    )

    log ReadRequestSent(_dst_eid, _target, _calldata)


@payable
@external
def lzReceive(
    _origin: lz.Origin,
    _guid: bytes32,
    _message: Bytes[lz.LZ_MESSAGE_SIZE_CAP],
    _executor: address,
    _extraData: Bytes[64],
) -> bool:
    """
    @notice Handle both regular messages and read responses
    """

    # Verify message source
    assert lz._lz_receive(_origin, _guid, _message, _executor, _extraData)

    if lz._is_read_response(_origin):
        # Handle read response
        message: String[128] = convert(_message, String[128])
        log ReadResponseReceived(_origin.srcEid, message)
    else:
        # Handle regular message
        message: String[128] = convert(_message, String[128])
        log MessageReceived(_origin.srcEid, message)

    return True


@view
@external
def dummy_endpoint(_input: uint256) -> uint256:
    return 2 * _input
