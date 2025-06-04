# pragma version 0.4.2

"""
@title OApp (LayerZero V2 OApp Standard)

@notice Vyper implementation of LayerZero OApp standard.
This contract implements the OApp interface for cross-chain messaging via LayerZero.
It combines the functionality of OAppCore, OAppSender, OAppReceiver, and OAppRead
into a single contract.

To use _quote/_lzSend, you must provide _options.
To build options, OptionsBuilder.vy should be used in your app.

To use lzRead functionality, you must use ReadCmdCodecV1.vy to encode read requests.

@dev Vyper implementation differs from Solidity OApp in:
- message size limits are handled differently (Vyper does not allow infinite bytes arrays, must be capped)
- fees are handled differently (payNative, payLzToken are inlined and allow many sends in single tx)


@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

################################################################
#                            MODULES                           #
################################################################

# Ownership management. Must be initialized in main contract.
from snekmate.auth import ownable

uses: ownable

# Vyper-specific constants
from . import VyperConstants as constants

################################################################
#                         INTERFACES                           #
################################################################

# ERC20 interface is needed for lzToken fee payment
from ethereum.ercs import IERC20

# LayerZero EndpointV2 interface
interface ILayerZeroEndpointV2:
    def quote(_params: MessagingParams, _sender: address) -> MessagingFee: view
    def send(_params: MessagingParams, _refundAddress: address) -> MessagingReceipt: payable
    def setDelegate(_delegate: address): nonpayable
    def eid() -> uint32: view
    def lzToken() -> address: view


################################################################
#                           EVENTS                            #
################################################################

event PeerSet:
    eid: uint32
    peer: bytes32


################################################################
#                           CONSTANTS                          #
################################################################

# Message size limits
MAX_MESSAGE_SIZE: constant(uint256) = constants.MAX_MESSAGE_SIZE
MAX_OPTIONS_TOTAL_SIZE: constant(uint256) = constants.MAX_OPTIONS_TOTAL_SIZE
MAX_EXTRA_DATA_SIZE: constant(uint256) = constants.MAX_EXTRA_DATA_SIZE

# Offspec constant, useful for read messages detection
READ_CHANNEL_THRESHOLD: constant(
    uint32
) = 4294965694  # max(uint32)-1601, 1600 channels reserved for read


################################################################
#                           STORAGE                            #
################################################################

# The LayerZero endpoint associated with the given OApp
endpoint: public(immutable(ILayerZeroEndpointV2))

# Mapping to store peers associated with corresponding endpoints
peers: public(HashMap[uint32, bytes32])

################################################################
#                           STRUCTS                            #
################################################################

struct MessagingParams:
    dstEid: uint32
    receiver: bytes32
    message: Bytes[MAX_MESSAGE_SIZE]
    options: Bytes[MAX_OPTIONS_TOTAL_SIZE]
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


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__(_endpoint: address, _delegate: address):
    """
    @notice Initialize OApp with endpoint and delegate
    @param _endpoint LayerZero endpoint address
    @param _delegate Address that can manage LZ configurations
    """
    assert _endpoint != empty(address), "Invalid endpoint"
    assert _delegate != empty(address), "Invalid delegate"

    # Set up endpoint
    endpoint = ILayerZeroEndpointV2(_endpoint)

    # Set delegate for endpoint config
    extcall endpoint.setDelegate(_delegate)


################################################################
#                           OAppCore                           #
################################################################

@external
def setPeer(_eid: uint32, _peer: bytes32):
    """
    @notice Sets the peer address (OApp instance) for a corresponding endpoint.
    @param _eid The endpoint ID.
    @param _peer The address of the peer to be associated with the corresponding endpoint.
    @dev Only the owner/admin of the OApp can call this function.
    @dev Indicates that the peer is trusted to send LayerZero messages to this OApp.
    @dev Set this to bytes32(0) to remove the peer address.
    @dev Peer is a bytes32 to accommodate non-evm chains.
    """
    ownable._check_owner()

    self._setPeer(_eid, _peer)


@internal
def _setPeer(_eid: uint32, _peer: bytes32):
    """
    @notice Internal function to set peer address
    @param _eid The endpoint ID.
    @param _peer The address of the peer to be associated with the corresponding endpoint.
    """
    self.peers[_eid] = _peer

    log PeerSet(eid=_eid, peer=_peer)


@view
@internal
def _getPeerOrRevert(_eid: uint32) -> bytes32:
    """
    @notice Internal function to get the peer address associated with a specific endpoint;
    reverts if NOT set.
    @param _eid The endpoint ID.
    @return peer The address of the peer associated with the specified endpoint.
    """
    peer: bytes32 = self.peers[_eid]
    assert peer != empty(bytes32), "OApp: no peer"
    return peer


@external
def setDelegate(_delegate: address):
    """
    @notice Sets the delegate address for the OApp.
    @param _delegate The address of the delegate to be set.
    @dev Only the owner/admin of the OApp can call this function.
    @dev Provides the ability for a delegate to set configs, on behalf of the OApp,
    directly on the Endpoint contract.
    """
    ownable._check_owner()

    extcall endpoint.setDelegate(_delegate)


################################################################
#                           OAppRead                           #
################################################################

@external
def setReadChannel(_channelId: uint32, _active: bool):
    """
    @notice Set or unset a read channel for this OApp
    @param _channelId The channel ID to use for read requests
    @param _active Whether to activate or deactivate the channel
    """
    ownable._check_owner()

    peer: bytes32 = convert(self, bytes32) if _active else convert(empty(address), bytes32)
    self._setPeer(_channelId, peer)


################################################################
#                         OAppReceiver                         #
################################################################

# Vyper-specific:
# oAppVersion - not implemented

@external
@view
def isComposeMsgSender(
    _origin: Origin, _message: Bytes[MAX_MESSAGE_SIZE], _sender: address
) -> bool:
    """
    @notice Indicates whether an address is an approved composeMsg sender to the Endpoint.
    @param _origin The origin information containing the source endpoint and sender address.
    @param _message The lzReceive payload.
    @param _sender The sender address.
    @return isSender Is a valid sender.
    """
    return _sender == self


@external
@view
def allowInitializePath(_origin: Origin) -> bool:
    """
    @notice Checks if the path initialization is allowed based on the provided origin.
    @param _origin The origin information containing the source endpoint and sender address.
    @return Whether the path has been initialized.
    @dev This indicates to the endpoint that the OApp has enabled msgs for this particular path to be received.
    @dev This defaults to assuming if a peer has been set, its initialized.
    """
    return self.peers[_origin.srcEid] == _origin.sender


@external
@pure
def nextNonce(_srcEid: uint32, _sender: bytes32) -> uint64:
    """
    @dev Vyper-specific: If your app relies on ordered execution, you must change this function.

    @notice Retrieves the next nonce for a given source endpoint and sender address.
    @dev _srcEid The source endpoint ID.
    @dev _sender The sender address.
    @return nonce The next nonce.
    @dev The path nonce starts from 1. If 0 is returned it means that there is NO nonce ordered enforcement.
    @dev Is required by the off-chain executor to determine the OApp expects msg execution is ordered.
    @dev This is also enforced by the OApp.
    @dev By default this is NOT enabled. ie. nextNonce is hardcoded to return 0.
    """
    return 0


@internal
@view
def _lzReceive(
    _origin: Origin,
    _guid: bytes32,
    _message: Bytes[MAX_MESSAGE_SIZE],
    _executor: address,
    _extraData: Bytes[MAX_EXTRA_DATA_SIZE],
):
    """
    @dev Vyper-specific: This must be called first in external lzReceive implementation.
    Name changed to _lzReceive due to internal nature of the function.

    @notice Entry point for receiving messages or packets from the endpoint.
    @param _origin The origin information containing the source endpoint and sender address.
        - srcEid: The source chain endpoint ID.
        - sender: The sender address on the src chain.
        - nonce: The nonce of the message.
    @param _guid The unique identifier for the received LayerZero message.
    @param _message The payload of the received message.
    @param _executor The address of the executor for the received message.
    @param _extraData Additional arbitrary data provided by the corresponding executor.
    """
    # Verify that the sender is the endpoint
    assert msg.sender == endpoint.address, "OApp: only endpoint"

    # Verify that the message comes from a trusted peer
    assert self._getPeerOrRevert(_origin.srcEid) == _origin.sender, "OApp: invalid sender"


################################################################
#                         OAppSender                           #
################################################################

# Vyper-specific:
# oAppVersion - not implemented

@internal
@view
def _quote(
    _dstEid: uint32,
    _message: Bytes[MAX_MESSAGE_SIZE],
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE],
    _payInLzToken: bool,
) -> MessagingFee:
    """
    @dev Internal function to interact with the LayerZero EndpointV2.quote() for fee calculation.
    @param _dstEid The destination endpoint ID.
    @param _message The message payload.
    @param _options Additional options for the message.
    @param _payInLzToken Flag indicating whether to pay the fee in LZ tokens.
    @return fee The calculated MessagingFee for the message.
            - nativeFee: The native fee for the message.
            - lzTokenFee: The LZ token fee for the message.
    """

    return staticcall endpoint.quote(
        MessagingParams(
            dstEid=_dstEid,
            receiver=self._getPeerOrRevert(_dstEid),
            message=_message,
            options=_options,
            payInLzToken=_payInLzToken,
        ),
        self,
    )


@internal
@payable
def _lzSend(
    _dstEid: uint32,
    _message: Bytes[MAX_MESSAGE_SIZE],
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE],
    _fee: MessagingFee,
    _refundAddress: address,
) -> MessagingReceipt:
    """
    @dev Vyper-specific: fees are treated differently than in Solidity OApp.
        - _payNative and _payLzToken are inlined.
        - Multiple sends are supported within single transaction (msg.value >= native_fee) instead of '=='.

    @dev Internal function to interact with the LayerZero EndpointV2.send() for sending a message.
    @param _dstEid The destination endpoint ID.
    @param _message The message payload.
    @param _options Additional options for the message.
    @param _fee The calculated LayerZero fee for the message.
        - nativeFee: The native fee.
        - lzTokenFee: The lzToken fee.
    @param _refundAddress The address to receive any excess fee values sent to the endpoint.
    @return receipt The receipt for the sent message.
        - guid: The unique identifier for the sent message.
        - nonce: The nonce of the sent message.
        - fee: The LayerZero fee incurred for the message.
    """
    # Get the peer address for the destination or revert if not set
    peer: bytes32 = self._getPeerOrRevert(_dstEid)

    # Handle native fee
    native_fee: uint256 = _fee.nativeFee
    if native_fee > 0:
        assert msg.value >= native_fee, "OApp: not enough fee"

    lzToken_fee: uint256 = _fee.lzTokenFee
    if lzToken_fee > 0:
        # Pay LZ token fee by sending tokens to the endpoint.
        lzToken: address = staticcall endpoint.lzToken()
        assert lzToken != empty(address), "OApp: LZ token unavailable"
        extcall IERC20(lzToken).transferFrom(msg.sender, endpoint.address, lzToken_fee)

    return extcall endpoint.send(
        MessagingParams(
            dstEid=_dstEid,
            receiver=peer,
            message=_message,
            options=_options,
            payInLzToken=_fee.lzTokenFee > 0,
        ),
        _refundAddress,
        value=native_fee,
    )
