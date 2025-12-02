# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title LayerZero Block Relay

@notice Layer Zero messenger for block hashes.
This contract should be deployed on multiple chains along with BlockOracle and MainnetBlockView.

Main functionality includes requesting lzRead of recent ethereum mainnet blockhashes from MainnetBlockView.
Upon receiving LZ message in lzReceive, the blockhash is committed to the BlockOracle, and if it was a read request,
the contract will attempt to broadcast the blockhash to other chains.

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
    def get_block_hash(block_number: uint256) -> bytes32: view


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
from ..modules.oapp_vyper.src import OApp  # main module
from ..modules.oapp_vyper.src import OptionsBuilder  # module for creating options
from ..modules.oapp_vyper.src import ReadCmdCodecV1  # module for reading commands

initializes: OApp[ownable := ownable]

exports: (
    OApp.endpoint,
    OApp.peers,
    OApp.setPeer,
    OApp.setDelegate,
    OApp.isComposeMsgSender,
    OApp.allowInitializePath,
    OApp.nextNonce,
)

################################################################
#                           CONSTANTS                          #
################################################################

MAX_N_BROADCAST: constant(uint256) = 32
GET_BLOCKHASH_SELECTOR: constant(Bytes[4]) = method_id("get_blockhash(uint256,bool)")
READ_RETURN_SIZE: constant(uint32) = 64

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

# Structs for cached broadcast info
struct BroadcastTarget:
    eid: uint32
    fee: uint256

struct BroadcastData:
    targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]
    gas_limit: uint128

# Broadcast targets
broadcast_data: HashMap[bytes32, BroadcastData]  # guid -> (targets: (eid, fee), gas_limit)

# lzRead received blocks
received_blocks: HashMap[uint256, bytes32]  # block_number -> block_hash

################################################################
#                            EVENTS                            #
################################################################

event BlockHashBroadcast:
    block_number: indexed(uint256)
    block_hash: indexed(bytes32)
    targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]


################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__(
    _endpoint: address,
):
    """
    @notice Initialize contract with core settings
    @dev Can only be called once, assumes caller is owner, sets as delegate
    @param _endpoint LayerZero endpoint address
    @param _lz_receive_gas_limit Gas limit for lzReceive
    """
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)  # origin to enable createx deployment

    OApp.__init__(_endpoint, tx.origin)  # origin also set as delegate

################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def set_read_config(
    _is_enabled: bool, _read_channel: uint32, _mainnet_eid: uint32, _mainnet_view: address
):
    """
    @notice Configure read functionality
    @param _is_enabled Whether this contract can initiate reads
    @param _read_channel LZ read channel ID
    @param _mainnet_eid Mainnet endpoint ID
    @param _mainnet_view MainnetBlockView contract address
    """
    ownable._check_owner()

    assert _read_channel > OApp.READ_CHANNEL_THRESHOLD, "Invalid read channel"

    assert (_is_enabled and _mainnet_eid != 0 and _mainnet_view != empty(address)) or (
        not _is_enabled and _mainnet_eid == 0 and _mainnet_view == empty(address)
    ), "Invalid read config"

    # Clean up old peer if switching channels while read is enabled
    # This prevents leaving stale peer mappings when changing read channels
    if self.read_enabled and self.read_channel != _read_channel:
        OApp._setPeer(self.read_channel, convert(empty(address), bytes32))

    self.read_enabled = _is_enabled
    self.read_channel = _read_channel
    self.mainnet_eid = _mainnet_eid
    self.mainnet_block_view = _mainnet_view

    peer: bytes32 = convert(self, bytes32) if _is_enabled else convert(empty(address), bytes32)
    OApp._setPeer(_read_channel, peer)


@external
def set_peers(_eids: DynArray[uint32, MAX_N_BROADCAST], _peers: DynArray[address, MAX_N_BROADCAST]):
    """
    @notice Set peers for a corresponding endpoints. Batched version of OApp.setPeer that accept address (EVM only).
    @param _eids The endpoint IDs.
    @param _peers Addresses of the peers to be associated with the corresponding endpoints.
    """
    ownable._check_owner()

    assert len(_eids) == len(_peers), "Invalid peer arrays"
    for i: uint256 in range(0, len(_eids), bound=MAX_N_BROADCAST):
        OApp._setPeer(_eids[i], convert(_peers[i], bytes32))


@external
def set_block_oracle(_oracle: address):
    """
    @notice Set the block oracle address
    @param _oracle Block oracle address
    """
    ownable._check_owner()

    self.block_oracle = IBlockOracle(_oracle)


@external
def withdraw_eth(_amount: uint256):
    """
    @notice Withdraw ETH from contract
    @dev ETH can be accumulated from LZ refunds
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


@internal
@view
def _prepare_read_request(_block_number: uint256) -> Bytes[OApp.MAX_MESSAGE_SIZE]:
    """
    @notice Prepare complete read request message for MainnetBlockView
    @param _block_number Block number to request (0 for latest)
    @return Prepared LayerZero message bytes
    """
    # 1. Build calldata
    calldata: Bytes[ReadCmdCodecV1.MAX_CALLDATA_SIZE] = abi_encode(
        _block_number, True, method_id=GET_BLOCKHASH_SELECTOR
    )

    # 2. Prepare ReadCmdRequestV1 struct
    request: ReadCmdCodecV1.EVMCallRequestV1 = ReadCmdCodecV1.EVMCallRequestV1(
        appRequestLabel=1,
        targetEid=self.mainnet_eid,
        isBlockNum=False,
        blockNumOrTimestamp=convert(block.timestamp, uint64),
        confirmations=1, # low confirmations because MainnetBlockView returns aged blockhashes
        to=self.mainnet_block_view,
        callData=calldata,
    )

    # 3. Encode request
    encoded_message: Bytes[ReadCmdCodecV1.MAX_MESSAGE_SIZE] = ReadCmdCodecV1.encode(
        1, [request]
    )  # 1 is _appCmdLabel
    # dev: ReadCmdCodecV1.MAX_MESSAGE_SIZE is opposed to OApp.MAX_MESSAGE_SIZE intentionally so code fails if they are not equal

    return encoded_message


@internal
@payable
def _request_block_hash(
    _block_number: uint256,
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _lz_receive_gas_limit: uint128,
    _read_gas_limit: uint128,
):
    """
    @notice Internal function to request block hash from mainnet and broadcast to specified targets
    @param _block_number Block number to request
    @param _target_eids Target EIDs to broadcast to
    @param _target_fees Target fees to pay per broadcast
    @param _lz_receive_gas_limit Gas limit for lzReceive
    @param _read_gas_limit Gas limit for read operation
    """

    # Store target EIDs and fees for lzReceive
    cached_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_eids), bound=MAX_N_BROADCAST):
        cached_targets.append(BroadcastTarget(eid=_target_eids[i], fee=_target_fees[i]))
        sum_target_fees += _target_fees[i]

    assert sum_target_fees <= msg.value, "Insufficient value" # dev: check is here because we sum here

    message: Bytes[OApp.MAX_MESSAGE_SIZE] = self._prepare_read_request(_block_number)

    # Create options using OptionsBuilder module
    options: Bytes[OptionsBuilder.MAX_OPTIONS_TOTAL_SIZE] = OptionsBuilder.newOptions()
    options = OptionsBuilder.addExecutorLzReadOption(
        options, _read_gas_limit, READ_RETURN_SIZE, convert(sum_target_fees, uint128)
    )

    # Send message
    fees: OApp.MessagingFee = OApp.MessagingFee(nativeFee=msg.value, lzTokenFee=0)
    # Fees = read fee + broadcast fees (value of read return message)
    receipt: OApp.MessagingReceipt = OApp._lzSend(
        self.read_channel, message, options, fees, msg.sender # dev: refund excess fee to sender
    )

    # Store targets for lzReceive using receipt.guid as key
    self.broadcast_data[receipt.guid] = BroadcastData(
        targets=cached_targets,
        gas_limit=_lz_receive_gas_limit,
    )


@internal
def _broadcast_block(
    _block_number: uint256,
    _block_hash: bytes32,
    _broadcast_data: BroadcastData,
    _refund_address: address,
):
    """
    @notice Internal function to broadcast block hash to multiple chains
    @param _block_number Block number to broadcast
    @param _block_hash Block hash to broadcast
    @param _broadcast_data Data for broadcasting
    @param _refund_address Excess fees receiver
    """
    message: Bytes[OApp.MAX_MESSAGE_SIZE] = abi_encode(_block_number, _block_hash)

    # Сreate options using OptionsBuilder module (same options for all targets)
    options: Bytes[OptionsBuilder.MAX_OPTIONS_TOTAL_SIZE] = OptionsBuilder.newOptions()
    options = OptionsBuilder.addExecutorLzReceiveOption(
        options, _broadcast_data.gas_limit, 0
    )

    for target: BroadcastTarget in _broadcast_data.targets:
        # Skip if peer is not set
        if OApp.peers[target.eid] == empty(bytes32):
            continue

        # Send message
        fees: OApp.MessagingFee = OApp.MessagingFee(nativeFee=target.fee, lzTokenFee=0)
        OApp._lzSend(target.eid, message, options, fees, _refund_address)

    log BlockHashBroadcast(
        block_number=_block_number,
        block_hash=_block_hash,
        targets=_broadcast_data.targets,
    )


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@external
@payable
@reentrant
def __default__():
    """
    @notice Default function to receive ETH
    @dev This is needed to receive refunds from LayerZero
    """
    pass


@external
@view
def quote_read_fee(
    _read_gas_limit: uint128,
    _value: uint128,
) -> uint256:
    """
    @notice Quote fee for reading block hash from mainnet
    @param _read_gas_limit Gas to be provided in return message
    @param _value Value to be provided in return message
    @return Fee in native tokens required for the read operation
    """
    assert self.read_enabled, "Read not enabled - call set_read_config"

    message: Bytes[OApp.MAX_MESSAGE_SIZE] = self._prepare_read_request(0) # dev: 0 for latest block

    # Create options using OptionsBuilder module
    options: Bytes[OptionsBuilder.MAX_OPTIONS_TOTAL_SIZE] = OptionsBuilder.newOptions()
    options = OptionsBuilder.addExecutorLzReadOption(
        options, _read_gas_limit, READ_RETURN_SIZE, _value
    )

    return OApp._quote(
        self.read_channel,
        message,
        options,
        False,
    ).nativeFee


@external
@view
def quote_broadcast_fees(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _lz_receive_gas_limit: uint128,
) -> DynArray[uint256, MAX_N_BROADCAST]:
    """
    @notice Quote fees for broadcasting block hash to specified targets
    @param _target_eids List of chain IDs to broadcast to
    @param _lz_receive_gas_limit Gas limit for lzReceive
    @return Array of fees per target chain (0 if target not configured)
    """
    # Prepare dummy broadcast message (uint256 number, bytes32 hash)
    message: Bytes[OApp.MAX_MESSAGE_SIZE] = abi_encode(empty(uint256), empty(bytes32))

    # Prepare array of fees per chain
    fees: DynArray[uint256, MAX_N_BROADCAST] = []

    # Prepare options (same for all targets)
    options: Bytes[OptionsBuilder.MAX_OPTIONS_TOTAL_SIZE] = OptionsBuilder.newOptions()
    options = OptionsBuilder.addExecutorLzReceiveOption(options, _lz_receive_gas_limit, 0)

    # Cycle through targets
    for eid: uint32 in _target_eids:
        target: bytes32 = OApp.peers[eid]  # Use peers directly
        if target == empty(bytes32):
            fees.append(0)
            continue

        # Get fee for target EID and append to array
        fees.append(OApp._quote(eid, message, options, False).nativeFee)

    return fees


@external
@payable
def request_block_hash(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _lz_receive_gas_limit: uint128,
    _read_gas_limit: uint128,
    _block_number: uint256 = 0,
):
    """
    @notice Request block hash from mainnet and broadcast to specified targets
    @param _target_eids List of chain IDs to broadcast to
    @param _target_fees List of fees per chain (must match _target_eids length)
    @param _lz_receive_gas_limit Gas limit for lzReceive (same for all targets)
    @param _read_gas_limit Gas limit for read operation
    @param _block_number Optional block number (0 means latest)
    @dev User must ensure msg.value is sufficient:
         - must cover read fee (quote_read_fee)
         - must cover broadcast fees (quote_broadcast_fees)
    """

    assert self.read_enabled, "Read not enabled"
    assert len(_target_eids) == len(_target_fees), "Length mismatch"

    self._request_block_hash(
        _block_number,
        _target_eids,
        _target_fees,
        _lz_receive_gas_limit,
        _read_gas_limit,
    )


@external
@payable
def broadcast_latest_block(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _lz_receive_gas_limit: uint128,
):
    """
    @notice Broadcast latest confirmed block hash to specified chains
    @param _target_eids List of chain IDs to broadcast to
    @param _target_fees List of fees per chain (must match _target_eids length)
    @param _lz_receive_gas_limit Gas limit for lzReceive (same for all targets)
    @dev Only broadcast what was received via lzRead to prevent potentially malicious hashes from other sources
    """

    assert self.read_enabled, "Can only broadcast from read-enabled chains"
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    assert len(_target_eids) == len(_target_fees), "Length mismatch"

    # Get latest block from oracle
    block_number: uint256 = staticcall self.block_oracle.last_confirmed_block_number()
    block_hash: bytes32 = staticcall self.block_oracle.get_block_hash(block_number)
    assert block_hash != empty(bytes32), "No confirmed blocks"

    # Only broadcast if this block was received via lzRead
    assert self.received_blocks[block_number] == block_hash, "Unknown source"

    # Prepare broadcast targets
    broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_eids), bound=MAX_N_BROADCAST):
        broadcast_targets.append(BroadcastTarget(eid=_target_eids[i], fee=_target_fees[i]))
        sum_target_fees += _target_fees[i]

    assert sum_target_fees <= msg.value, "Insufficient message value"

    self._broadcast_block(
        block_number,
        block_hash,
        BroadcastData(targets=broadcast_targets, gas_limit=_lz_receive_gas_limit),
        msg.sender,
    )


@payable
@external
def lzReceive(
    _origin: OApp.Origin,
    _guid: bytes32,
    _message: Bytes[OApp.MAX_MESSAGE_SIZE],
    _executor: address,
    _extraData: Bytes[OApp.MAX_EXTRA_DATA_SIZE],
):
    """
    @notice Handle messages: read responses, and regular messages
    @dev Two types of messages:
         1. Read responses (from read channel)
         2. Regular messages (block hash broadcasts from other chains)
    @param _origin Origin information containing srcEid, sender, and nonce
    @param _guid Global unique identifier for the message
    @param _message The encoded message payload containing block number and hash
    @param _executor Address of the executor for the message
    @param _extraData Additional data passed by the executor
    """
    # Verify message source
    OApp._lzReceive(_origin, _guid, _message, _executor, _extraData)

    if _origin.srcEid == self.read_channel:
        # Only handle read response if read is enabled
        assert self.read_enabled, "Read not enabled"
        # Decode block hash and number from response
        block_number: uint256 = 0
        block_hash: bytes32 = empty(bytes32)
        block_number, block_hash = abi_decode(_message, (uint256, bytes32))
        if block_hash == empty(bytes32):
            return  # Invalid response

        # Store received block hash
        self.received_blocks[block_number] = block_hash

        # Commit block hash to oracle
        self._commit_block(block_number, block_hash)

        broadcast_data: BroadcastData = self.broadcast_data[_guid]

        if len(broadcast_data.targets) > 0:
            # Verify that attached value covers requested broadcast fees
            total_fee: uint256 = 0
            for target: BroadcastTarget in broadcast_data.targets:
                total_fee += target.fee
            assert msg.value >= total_fee, "Insufficient msg.value"

            # Perform broadcast
            self._broadcast_block(
                block_number,
                block_hash,
                broadcast_data,
                self, # dev: refund excess fee to self
            )
    else:
        # Regular message - decode and commit block hash
        block_number: uint256 = 0
        block_hash: bytes32 = empty(bytes32)
        block_number, block_hash = abi_decode(_message, (uint256, bytes32))
        self._commit_block(block_number, block_hash)
