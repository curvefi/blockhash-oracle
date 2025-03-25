# pragma version 0.4.1
# pragma optimize gas

"""
@title LayerZero Block Relay

@notice Layer Zero messenger for block hashes.
This contract should be deployed on multiple chains along with BlockOracle and MainnetBlockView.

Main functionality includes requesting lzRead of recent ethereum mainnet blockhashes from MainnetBlockView.
Upon receiving LZ message in lzReceive, the blockhash is committed to the BlockOracle, and if it was a read request,
the contract will attempt to broadcast the blockhash to other chains via lzSend.

If chain is read-enabled, it will be able to read the blockhash from MainnetBlockView and broadcast it to other chains.
If chain is not read-enabled, it will only be able to receive blockhashes from other chains.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""


################################################################
#                           INTERFACES                         #
################################################################

interface IBlockOracle:
    def commit_block(block_number: uint256, block_hash: bytes32) -> bool: nonpayable
    def last_confirmed_block_number() -> uint256: view
    def block_hash(block_number: uint256) -> bytes32: view


################################################################
#                            MODULES                           #
################################################################

# Import ownership management
from snekmate.auth import ownable

initializes: ownable
exports: (
    ownable.owner,
    ownable.transfer_ownership,
    ownable.renounce_ownership,
)

# Import LayerZero module for cross-chain messaging
from ..modules.oapp_vyper import OApp  # main module
from ..modules.oapp_vyper import OptionsBuilder  # module for creating options
from ..modules.oapp_vyper import ReadCmdCodecV1  # module for reading commands

initializes: OApp[ownable := ownable]

exports: (
    OApp.endpoint,
    OApp.peers,
    OApp.setPeer,
    OApp.setDelegate,
    OApp.setReadChannel,
    OApp.isComposeMsgSender,
    OApp.allowInitializePath,
    OApp.nextNonce,
)

################################################################
#                           CONSTANTS                          #
################################################################

MAX_N_BROADCAST: constant(uint256) = 32
GET_BLOCKHASH_SELECTOR: constant(Bytes[4]) = method_id("get_blockhash(uint256,bool)")


################################################################
#                            STORAGE                           #
################################################################

# Read configuration
read_enabled: public(bool)
read_channel: public(uint32)
mainnet_eid: public(uint32)
mainnet_block_view: public(address)

# Block oracle
block_oracle: public(IBlockOracle)

# Refund address
default_lz_refund_address: public(address)

# Default gas limit
default_gas_limit: public(uint128)

# Struct for cached broadcast info
struct BroadcastTarget:
    eid: uint32
    fee: uint256


# Broadcast targets
broadcast_targets: HashMap[bytes32, DynArray[BroadcastTarget, MAX_N_BROADCAST]]  # guid -> targets

# lzRead received blocks
received_blocks: HashMap[uint256, bytes32]  # block_number -> block_hash

################################################################
#                            EVENTS                            #
################################################################

event BlockHashBroadcast:
    source_eid: uint32
    block_number: uint256
    block_hash: bytes32
    targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]


################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__(
    _endpoint: address,
    _gas_limit: uint256,
    _read_channel: uint32,
    # Can optionally initialize with peers (32 max for initial deployment)
    _peer_eids: DynArray[uint32, 32],
    _peers: DynArray[bytes32, 32],
):
    """
    @notice Initialize contract with core settings
    @dev Can only be called once, assumes caller is owner, sets as delegate
    @param _endpoint LayerZero endpoint address
    @param _gas_limit Default gas limit for cross-chain messages
    @param _read_channel LZ Read channel ID
    @param _peer_eids Array of peer EIDs
    @param _peers Array of peer addresses
    @dev Note that peers are bytes32 (LZ specs), convert accordingly
    we could convert inside, but OApp.setPeer requires bytes32,
    so we force devs to have conversion script
    """
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)  # origin to enable createx deployment

    OApp.__init__(_endpoint, tx.origin)  # origin also set as delegate

    self.default_lz_refund_address = self

    assert len(_peer_eids) == len(_peers), "Invalid peer arrays"
    for i: uint256 in range(0, len(_peer_eids), bound=32):
        OApp._setPeer(_peer_eids[i], _peers[i])


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def set_default_gas(_gas_limit: uint128):
    """
    @notice Update default gas limit for messages
    @param _gas_limit New gas limit
    """

    ownable._check_owner()
    self.default_gas_limit = _gas_limit


@external
def set_read_config(
    _is_enabled: bool, read_channel: uint32, _mainnet_eid: uint32, _mainnet_view: address
):
    """
    @notice Configure read functionality
    @param _is_enabled Whether this contract can initiate reads
    @param read_channel LZ read channel ID
    @param _mainnet_eid Mainnet endpoint ID
    @param _mainnet_view MainnetBlockView contract address
    """
    ownable._check_owner()

    assert read_channel > OApp.READ_CHANNEL_THRESHOLD, "Invalid read channel"

    assert (_is_enabled and _mainnet_eid != 0 and _mainnet_view != empty(address)) or (
        not _is_enabled and _mainnet_eid == 0 and _mainnet_view == empty(address)
    ), "Invalid read config"

    self.read_enabled = _is_enabled
    self.read_channel = read_channel
    self.mainnet_eid = _mainnet_eid
    self.mainnet_block_view = _mainnet_view

    peer: bytes32 = convert(self, bytes32) if _is_enabled else convert(empty(address), bytes32)
    OApp._setPeer(read_channel, peer)


@external
def set_block_oracle(_oracle: address):
    """
    @notice Set the block oracle address
    @param _oracle Block oracle address
    """
    ownable._check_owner()
    self.block_oracle = IBlockOracle(_oracle)


@external
def set_default_lz_refund_address(_refund_address: address):
    """
    @notice Set default refund address for LayerZero operations
    @param _refund_address New refund address
    """
    ownable._check_owner()
    self.default_lz_refund_address = _refund_address


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
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
def _commit_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Commit block hash to oracle
    """
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    extcall self.block_oracle.commit_block(_block_number, _block_hash)


@view
@internal
def _prepare_read_request(_block_number: uint256) -> Bytes[OApp.MAX_MESSAGE_SIZE]:
    """
    @notice Prepare complete read request message for MainnetBlockView
    @param _block_number Block number to request (0 for latest)
    @return Prepared LayerZero message bytes
    """
    # Build calldata
    calldata: Bytes[ReadCmdCodecV1.MAX_CALLDATA_SIZE] = abi_encode(
        _block_number, True, method_id=GET_BLOCKHASH_SELECTOR
    )
    # step 1: prepare read message using ReadCmdCodecV1 module
    # A: prepare ReadCmdRequestV1 struct
    request: ReadCmdCodecV1.EVMCallRequestV1 = ReadCmdCodecV1.EVMCallRequestV1(
        appRequestLabel=1,
        targetEid=self.mainnet_eid,
        isBlockNum=False,
        blockNumOrTimestamp=convert(block.timestamp, uint64),
        confirmations=1,
        to=self.mainnet_block_view,
        callData=calldata,
    )
    # B: encode request
    encoded_message: Bytes[ReadCmdCodecV1.MAX_MESSAGE_SIZE] = ReadCmdCodecV1.encode(
        1, [request]
    )  # 1 is _appCmdLabel
    # dev: ReadCmdCodecV1.MAX_MESSAGE_SIZE is opposed to OApp.MAX_MESSAGE_SIZE intentionally so code fails if they are not equal

    return encoded_message


@internal
def _request_block_hash(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _block_number: uint256,
    _gas_limit: uint128,
    _request_msg_value: uint256,
    _refund_address: address,
):
    """
    @notice Internal function to request block hash from mainnet and broadcast to specified targets
    """
    assert self.read_enabled, "Read not enabled - can't broadcast"
    assert len(_target_eids) == len(_target_fees), "Length mismatch"

    # Cache target EIDs and fees for lzReceive
    cached_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_eids), bound=MAX_N_BROADCAST):
        cached_targets.append(BroadcastTarget(eid=_target_eids[i], fee=_target_fees[i]))
        sum_target_fees += _target_fees[i]

    message: Bytes[OApp.MAX_MESSAGE_SIZE] = self._prepare_read_request(_block_number)

    # Create options using OptionsBuilder module
    options: Bytes[OptionsBuilder.MAX_OPTIONS_TOTAL_SIZE] = OptionsBuilder.newOptions()
    options = OptionsBuilder.addExecutorLzReadOption(
        options, _gas_limit, 64, convert(sum_target_fees, uint128)
    )  # 64 is expected response size

    # Send message
    fees: OApp.MessagingFee = OApp.MessagingFee(nativeFee=_request_msg_value, lzTokenFee=0)
    receipt: OApp.MessagingReceipt = OApp._lzSend(
        self.read_channel, message, options, fees, _refund_address
    )

    self.broadcast_targets[receipt.guid] = cached_targets


@internal
def _broadcast_block(
    _block_number: uint256,
    _block_hash: bytes32,
    _broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST],
    _source_eid: uint32,
    _refund_address: address,
):
    """
    @notice Internal function to broadcast block hash to multiple chains
    @param _block_number Block number to broadcast
    @param _block_hash Block hash to broadcast
    @param _broadcast_targets Array of targets with their fees
    @param _source_eid Chain ID where the block hash originated from
    """
    message: Bytes[OApp.MAX_MESSAGE_SIZE] = abi_encode(_block_number, _block_hash)

    for target: BroadcastTarget in _broadcast_targets:
        # BroadcastTarget is a struct with .eid and .fee
        target_address: address = convert(OApp.peers[target.eid], address)  # Use peers directly
        if target_address == empty(address):
            continue


        # Сreate options using OptionsBuilder module
        options: Bytes[OptionsBuilder.MAX_OPTIONS_TOTAL_SIZE] = OptionsBuilder.newOptions()
        options = OptionsBuilder.addExecutorLzReceiveOption(options, self.default_gas_limit, 0)

        # Send message
        fees: OApp.MessagingFee = OApp.MessagingFee(nativeFee=target.fee, lzTokenFee=0)
        OApp._lzSend(target.eid, message, options, fees, _refund_address)

        log BlockHashBroadcast(
            source_eid=_source_eid,
            block_number=_block_number,
            block_hash=_block_hash,
            targets=_broadcast_targets,
        )


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@external
@payable
def __default__():
    """
    @notice Default function to receive ETH
    @dev This is needed to receive refunds from LayerZero
    """
    pass


# @view
# @external
# def quote_read_fee(
#     _block_number: uint256 = 0,
#     _gas_limit: uint256 = 0,
#     _value: uint256 = 0,
#     _data_size: uint32 = 64,
# ) -> uint256:
#     """
#     @notice Quote fee for reading block hash from mainnet
#     @param _block_number Optional block number (0 means latest)
#     @param _gas_limit Optional gas limit override
#     @return Fee in native tokens required for the read operation
#     """
#     assert self.read_enabled, "Read not enabled - call set_read_config"

#     message: Bytes[lz.MAX_MESSAGE_SIZE] = self._prepare_read_request(_block_number)

#     return lz._quote_lz_fee(
#         lz.LZ_READ_CHANNEL,
#         self,
#         message,
#         _gas_limit,
#         _value,
#         _data_size,  # Expected response size
#     )


# @view
# @external
# def quote_broadcast_fees(
#     _target_eids: DynArray[uint32, MAX_N_BROADCAST], _gas_limit: uint256 = 0
# ) -> DynArray[uint256, MAX_N_BROADCAST]:
#     """
#     @notice Quote fees for broadcasting block hash to specified targets
#     @param _target_eids List of chain IDs to broadcast to
#     @param _gas_limit Optional gas limit override
#     @return Array of fees per target chain (0 if target not configured)
#     """
#     # Prepare dummy broadcast message (uint256 number, bytes32 hash)
#     message: Bytes[lz.MAX_MESSAGE_SIZE] = abi_encode(empty(uint256), empty(bytes32))

#     # Get fees per chain
#     fees: DynArray[uint256, MAX_N_BROADCAST] = []

#     for eid: uint32 in _target_eids:
#         target: address = lz.LZ_PEERS[eid]  # Use LZ_PEERS directly
#         if target == empty(address):
#             fees.append(0)
#             continue

#         fee: uint256 = lz._quote_lz_fee(eid, target, message, _gas_limit)
#         fees.append(fee)

#     return fees


# @payable
# @external
# def request_block_hash(
#     _target_eids: DynArray[uint32, MAX_N_BROADCAST],
#     _target_fees: DynArray[uint256, MAX_N_BROADCAST],
#     _block_number: uint256 = 0,
#     _gas_limit: uint256 = 0,
# ):
#     """
#     @notice Request block hash from mainnet and broadcast to specified targets
#     @param _target_eids List of chain IDs to broadcast to
#     @param _target_fees List of fees per chain (must match _target_eids length)
#     @param _block_number Optional block number (0 means latest)
#     @param _gas_limit Optional gas limit override
#     @dev User must ensure msg.value is sufficient:
#          - must cover read fee (quote_read_fee)
#          - must cover broadcast fees (quote_broadcast_fees)
#     """
#     self._request_block_hash(
#         _target_eids,
#         _target_fees,
#         _block_number,
#         _gas_limit,
#         msg.value,  # Use full msg.value
#         msg.sender,  # Refund to sender
#     )


# @payable
# @external
# def broadcast_latest_block(
#     _target_eids: DynArray[uint32, MAX_N_BROADCAST],
#     _target_fees: DynArray[uint256, MAX_N_BROADCAST],
# ):
#     """
#     @notice Broadcast latest confirmed block hash to specified chains
#     @param _target_eids List of chain IDs to broadcast to
#     @param _target_fees List of fees per chain (must match _target_eids length)
#     @dev Only broadcast what was received via lzRead to prevent potentially malicious hashes from other sources
#     """

#     assert self.read_enabled, "Can only broadcast from read-enabled chains"
#     assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
#     assert len(_target_eids) == len(_target_fees), "Length mismatch"

#     # Get latest block from oracle
#     block_number: uint256 = staticcall self.block_oracle.last_confirmed_block_number()
#     block_hash: bytes32 = staticcall self.block_oracle.block_hash(block_number)
#     assert block_hash != empty(bytes32), "No confirmed blocks"

#     # Only broadcast if this block was received via lzRead
#     assert self.received_blocks[block_number] == block_hash

#     # Prepare broadcast targets
#     broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
#     for i: uint256 in range(0, len(_target_eids), bound=MAX_N_BROADCAST):
#         broadcast_targets.append(BroadcastTarget(eid=_target_eids[i], fee=_target_fees[i]))

#     self._broadcast_block(block_number, block_hash, broadcast_targets, lz.EID, msg.sender)


# @payable
# @external
# def lzReceive(
#     _origin: lz.Origin,
#     _guid: bytes32,
#     _message: Bytes[lz.MAX_MESSAGE_SIZE],
#     _executor: address,
#     _extraData: Bytes[64],
# ) -> bool:
#     """
#     @notice Handle messages: read responses, broadcast requests, and regular messages
#     @dev Three types of messages:
#          1. Read responses (from read channel)
#          2. Regular messages (block hash broadcasts)
#     """
#     # Verify message source
#     assert lz._lz_receive(_origin, _guid, _message, _executor, _extraData)

#     if lz._is_read_response(_origin):
#         # Only handle read response if read is enabled
#         assert self.read_enabled, "Read not enabled"
#         # Decode block hash and number from response
#         block_number: uint256 = 0
#         block_hash: bytes32 = empty(bytes32)
#         block_number, block_hash = abi_decode(_message, (uint256, bytes32))
#         if block_hash == empty(bytes32):
#             return True  # Invalid response


#         # Cache received block hash
#         self.received_blocks[block_number] = block_hash

#         # Commit block hash to oracle
#         self._commit_block(block_number, block_hash)

#         broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = self.broadcast_targets[
#             _guid
#         ]

#         if len(broadcast_targets) > 0:

#             # Verify that attached value covers requested broadcast fees
#             total_fee: uint256 = 0
#             for target: BroadcastTarget in broadcast_targets:
#                 total_fee += target.fee
#             assert msg.value >= total_fee, "Insufficient msg.value"

#             # Perform broadcast
#             self._broadcast_block(
#                 block_number,
#                 block_hash,
#                 broadcast_targets,
#                 _origin.srcEid,
#                 self.default_lz_refund_address,
#             )
#     else:
#         # Regular message - decode and commit block hash
#         block_number: uint256 = 0
#         block_hash: bytes32 = empty(bytes32)
#         block_number, block_hash = abi_decode(_message, (uint256, bytes32))
#         self._commit_block(block_number, block_hash)

#     return True
