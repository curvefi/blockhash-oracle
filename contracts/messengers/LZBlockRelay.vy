# pragma version ~=0.4
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

# Import LayerZero module for cross-chain messaging
from ..modules import LayerZeroV2 as lz

initializes: lz
exports: (
    lz.LZ_ENDPOINT,
    lz.LZ_PEERS,
    lz.LZ_DELEGATE,
    lz.LZ_READ_CHANNEL,
    lz.default_gas_limit,
    lz.nextNonce,
    lz.allowInitializePath,
    lz.get_configured_eids,
)

# Import ownership management
from snekmate.auth import ownable

initializes: ownable
exports: (
    ownable.owner,
    ownable.transfer_ownership,
    ownable.renounce_ownership,
)


################################################################
#                           CONSTANTS                          #
################################################################

MAX_N_BROADCAST: constant(uint256) = 32
GET_BLOCKHASH_SELECTOR: constant(Bytes[4]) = method_id("get_blockhash(uint256,bool)")
BROADCAST_REQUEST_MESSAGE: constant(Bytes[17]) = b"broadcast_request"


################################################################
#                            STORAGE                           #
################################################################

is_initialized: public(bool)

# Read configuration
is_read_enabled: public(bool)
mainnet_eid: public(uint32)
mainnet_block_view: public(address)

# Block oracle
block_oracle: public(IBlockOracle)

# Refund address
default_lz_refund_address: public(address)

# Struct for cached broadcast info
struct BroadcastTarget:
    eid: uint32
    fee: uint256


# Cached broadcast targets
cached_broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]


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
def __init__(_owner: address):
    """
    @notice Empty constructor for deterministic deployment
    """
    lz.__init__()
    ownable.__init__()
    ownable._transfer_ownership(_owner)


@external
def initialize(
    _endpoint: address,
    _gas_limit: uint256,
    _read_channel: uint32,
    # Can optionally initialize with peers
    _peer_eids: DynArray[uint32, lz.MAX_PEERS],
    _peers: DynArray[address, lz.MAX_PEERS],
    # Also can provide libs per peer (must provide lib types: 1 for lzsend, 2 for lzreceive)
    # We limit to 2 * MAX_PEERS because we have send and receive libs for each peer
    _oapps: DynArray[address, 2 * lz.MAX_PEERS],
    _channels: DynArray[uint32, 2 * lz.MAX_PEERS],
    _libs: DynArray[address, 2 * lz.MAX_PEERS],
    _lib_types: DynArray[uint16, 2 * lz.MAX_PEERS],
):
    """
    @notice Initialize contract with core settings
    @dev Can only be called once, assumes caller is owner, sets as delegate
    @param _endpoint LayerZero endpoint address
    @param _gas_limit Default gas limit for cross-chain messages
    @param _read_channel LZ Read channel ID
    """
    ownable._check_owner()
    assert not self.is_initialized, "Already initialized"
    assert _endpoint != empty(address), "Invalid endpoint"

    self.is_initialized = True
    self.default_lz_refund_address = self

    # Initialize LayerZero module
    lz._initialize(_endpoint, _gas_limit, _read_channel, _peer_eids, _peers)

    # Set owner as delegate
    lz._set_delegate(msg.sender)

    # Set libs if provided
    assert len(_channels) == len(_libs), "Libs-channels length mismatch"
    assert len(_libs) == len(_lib_types), "Libs-types length mismatch"
    for i: uint256 in range(0, len(_channels), bound=2 * lz.MAX_PEERS):
        if _lib_types[i] == 1:
            lz._set_send_lib(_channels[i], _libs[i])
        elif _lib_types[i] == 2:
            lz._set_receive_lib(_channels[i], _libs[i])
        else:
            raise ("Invalid lib type")


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
    _executor: address = empty(address),
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
        _executor,
    )


@external
def set_read_config(_is_enabled: bool, _mainnet_eid: uint32, _mainnet_view: address):
    """
    @notice Configure read functionality
    @param _is_enabled Whether this contract can initiate reads
    @param _mainnet_eid Mainnet endpoint ID
    @param _mainnet_view MainnetBlockView contract address
    """
    ownable._check_owner()
    self.is_read_enabled = _is_enabled
    self.mainnet_eid = _mainnet_eid
    self.mainnet_block_view = _mainnet_view


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
def _prepare_read_request(_block_number: uint256) -> Bytes[lz.LZ_MESSAGE_SIZE_CAP]:
    """
    @notice Prepare complete read request message for MainnetBlockView
    @param _block_number Block number to request (0 for latest)
    @return Prepared LayerZero message bytes
    """
    # Build calldata
    calldata: Bytes[lz.LZ_READ_CALLDATA_SIZE] = abi_encode(
        _block_number, True, method_id=GET_BLOCKHASH_SELECTOR
    )

    # Prepare read message
    return lz._prepare_read_message_bytes(
        self.mainnet_eid,  # _dst_eid
        self.mainnet_block_view,  # _target
        calldata,  # _calldata
        False,  # _isBlockNum, we use timestamp
        convert(block.timestamp, uint64),  # _blockNumOrTimestamp, we use latest timestamp
        1,  # _confirmations set to 1 because we read 'older' blocks that cant be affected by reorgs
    )


@internal
def _broadcast_block(
    _block_number: uint256,
    _block_hash: bytes32,
    _broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST],
    _source_eid: uint32,
    _refund_address: address = empty(address),
):
    """
    @notice Internal function to broadcast block hash to multiple chains
    @param _block_number Block number to broadcast
    @param _block_hash Block hash to broadcast
    @param _broadcast_targets Array of targets with their fees
    @param _source_eid Chain ID where the block hash originated from
    """
    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = abi_encode(_block_number, _block_hash)

    for target: BroadcastTarget in _broadcast_targets:
        # BroadcastTarget is a struct with .eid and .fee
        target_address: address = lz.LZ_PEERS[target.eid]  # Use LZ_PEERS directly
        if target_address == empty(address):
            continue

        lz._send_message(
            target.eid,  # _dstEid
            convert(target_address, bytes32),  # _receiver
            message,  # _message
            0,  # _gas_limit: Use default gas limit
            0,  # _lz_receive_value: No value to attach to receive call
            0,  # _data_size: Zero data size (not a read)
            target.fee,  # _request_msg_value: Use cached fee as send message value
            _refund_address,  # _refund_address: shouldn't refund executor
            False,  # _perform_fee_check: No fee check
        )

    log BlockHashBroadcast(_source_eid, _block_number, _block_hash, _broadcast_targets)


@internal
def _request_block_hash(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _block_number: uint256,
    _gas_limit: uint256,
    _request_msg_value: uint256,
    _refund_address: address,
):
    """
    @notice Internal function to request block hash from mainnet and broadcast to specified targets
    """
    assert self.is_read_enabled, "Read not enabled - call set_read_config"
    assert self.mainnet_block_view != empty(address), "Mainnet view not set - call set_read_config"
    assert len(_target_eids) == len(_target_fees), "Length mismatch"

    # Cache target EIDs and fees for lzReceive
    cached_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_eids), bound=MAX_N_BROADCAST):
        cached_targets.append(BroadcastTarget(eid=_target_eids[i], fee=_target_fees[i]))
        sum_target_fees += _target_fees[i]
    self.cached_broadcast_targets = cached_targets

    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = self._prepare_read_request(_block_number)

    # Send to read channel with enough value to cover broadcasts
    lz._send_message(
        lz.LZ_READ_CHANNEL,  # _dstEid
        convert(self, bytes32),  # _receiver
        message,  # _message
        _gas_limit,  # _gas_limit: Use default gas limit
        sum_target_fees,  # _lz_receive_value: Will be available in lzReceive (and pay for broadcasts)
        64,  # _data_size: Expected read size (uint256: block number, bytes32: block hash)
        _request_msg_value,  # _request_msg_value: Use provided value
        _refund_address,  # _refund_address: Refund unspent fees to specified address
        False,  # _perform_fee_check: No fee check
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


@view
@external
def quote_read_fee(
    _block_number: uint256 = 0,
    _gas_limit: uint256 = 0,
    _value: uint256 = 0,
    _data_size: uint32 = 64,
) -> uint256:
    """
    @notice Quote fee for reading block hash from mainnet
    @param _block_number Optional block number (0 means latest)
    @param _gas_limit Optional gas limit override
    @return Fee in native tokens required for the read operation
    """
    assert self.is_read_enabled, "Read not enabled - call set_read_config"
    assert self.mainnet_block_view != empty(address), "Mainnet view not set - call set_read_config"

    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = self._prepare_read_request(_block_number)

    return lz._quote_lz_fee(
        lz.LZ_READ_CHANNEL,
        empty(address),
        message,
        _gas_limit,
        _value,
        _data_size,  # Expected response size
    )


@view
@external
def quote_broadcast_fees(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST], _gas_limit: uint256 = 0
) -> DynArray[uint256, MAX_N_BROADCAST]:
    """
    @notice Quote fees for broadcasting block hash to specified targets
    @param _target_eids List of chain IDs to broadcast to
    @param _gas_limit Optional gas limit override
    @return Array of fees per target chain (0 if target not configured)
    """
    # Prepare dummy broadcast message (uint256 number, bytes32 hash)
    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = abi_encode(empty(uint256), empty(bytes32))

    # Get fees per chain
    fees: DynArray[uint256, MAX_N_BROADCAST] = []

    for eid: uint32 in _target_eids:
        target: address = lz.LZ_PEERS[eid]  # Use LZ_PEERS directly
        if target == empty(address):
            fees.append(0)
            continue

        fee: uint256 = lz._quote_lz_fee(eid, target, message, _gas_limit)
        fees.append(fee)

    return fees


@payable
@external
def request_block_hash(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _block_number: uint256 = 0,
    _gas_limit: uint256 = 0,
):
    """
    @notice Request block hash from mainnet and broadcast to specified targets
    @param _target_eids List of chain IDs to broadcast to
    @param _target_fees List of fees per chain (must match _target_eids length)
    @param _block_number Optional block number (0 means latest)
    @param _gas_limit Optional gas limit override
    @dev User must ensure msg.value is sufficient:
         - must cover read fee (quote_read_fee)
         - must cover broadcast fees (quote_broadcast_fees)
    """
    self._request_block_hash(
        _target_eids,
        _target_fees,
        _block_number,
        _gas_limit,
        msg.value,  # Use full msg.value
        msg.sender,  # Refund to sender
    )


@payable
@external
def broadcast_latest_block(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
):
    """
    @notice Broadcast latest confirmed block hash to specified chains
    @param _target_eids List of chain IDs to broadcast to
    @param _target_fees List of fees per chain (must match _target_eids length)
    @dev TODO must think of ways to prevent distribution of malicious block hashes
    If single chain oracle has wrong hash (compromised sequencer/committer) it can be used to broadcast malicious block hashes everywhere.
    Either rm this function completely or cache lz received hashes and only transmit them (+hashmap & assert)
    """
    assert self.is_read_enabled, "Can only broadcast from read-enabled chains"
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    assert len(_target_eids) == len(_target_fees), "Length mismatch"

    # Get latest block from oracle
    block_number: uint256 = staticcall self.block_oracle.last_confirmed_block_number()
    block_hash: bytes32 = staticcall self.block_oracle.block_hash(block_number)
    assert block_hash != empty(bytes32), "No confirmed blocks"

    # Prepare broadcast targets
    broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    for i: uint256 in range(0, len(_target_eids), bound=MAX_N_BROADCAST):
        broadcast_targets.append(BroadcastTarget(eid=_target_eids[i], fee=_target_fees[i]))

    self._broadcast_block(block_number, block_hash, broadcast_targets, lz.EID, msg.sender)


@payable
@external
def request_remote_read(
    _remote_eid: uint32,
    _read_fee: uint256,
    _broadcast_fee: uint256,
    _request_gas_limit: uint256 = 0,
):
    """
    @notice Request a chain to perform an lzread operation and broadcast the result back to us
    @param _remote_eid Chain ID to request the read from
    @param _read_fee Fee to cover the lzread operation on target chain
    @param _broadcast_fee Fee to cover broadcasting the result back to us
    @dev msg.value must cover both:
         - fee to send request to target chain
         - _read_fee + _broadcast_fee which will be used by target chain
    """
    # Prepare broadcast request message (magic bytes + fee)
    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = concat(
        BROADCAST_REQUEST_MESSAGE,  # 17 bytes
        convert(_broadcast_fee, bytes32),  # 32 bytes
    )

    # Send message to target chain
    lz._send_message(
        _remote_eid,  # _dstEid
        convert(
            lz.LZ_PEERS[_remote_eid], bytes32
        ),  # _receiver - can only be configured peer (self)
        message,  # _message
        _request_gas_limit,  # _gas_limit for read request
        _read_fee + _broadcast_fee,  # _lz_receive_value: must cover both read and broadcast
        0,  # _data_size: Zero data size (not a read)
        msg.value,  # _request_msg_value: Use full msg.value
        msg.sender,  # _refund_address: Refund to sender
        True,  # _perform_fee_check: Check fees
    )


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
    @notice Handle messages: read responses, broadcast requests, and regular messages
    @dev Three types of messages:
         1. Read responses (from read channel)
         2. Broadcast requests (magic bytes + fee)
         3. Regular messages (block hash broadcasts)
    @dev Broadcast request format:
         - First 17 bytes: BROADCAST_REQUEST_MESSAGE
         - Next 32 bytes: uint256 fee for return broadcast
    """
    # Verify message source
    assert lz._lz_receive(_origin, _guid, _message, _executor, _extraData)

    if lz._is_read_response(_origin):
        # Only handle read response if read is enabled
        assert self.is_read_enabled, "Read not enabled"

        # Decode block hash and number from response
        block_number: uint256 = 0
        block_hash: bytes32 = empty(bytes32)
        block_number, block_hash = abi_decode(_message, (uint256, bytes32))
        if block_hash == empty(bytes32):
            return True  # Invalid response

        self._commit_block(block_number, block_hash)

        # Get cached targets and broadcast if we have any
        broadcast_targets: DynArray[
            BroadcastTarget, MAX_N_BROADCAST
        ] = self.cached_broadcast_targets
        if len(broadcast_targets) > 0:
            # Perform broadcast and clear cache
            self._broadcast_block(
                block_number,
                block_hash,
                broadcast_targets,
                _origin.srcEid,
                self.default_lz_refund_address,
            )
            self.cached_broadcast_targets = empty(DynArray[BroadcastTarget, MAX_N_BROADCAST])
    elif slice(_message, 0, 17) == BROADCAST_REQUEST_MESSAGE:  # 17 + 32 bytes
        # Handle broadcast request - decode fee and trigger read
        broadcast_fee: uint256 = abi_decode(slice(_message, 17, 32), (uint256))

        # msg.value must cover both read and broadcast
        assert broadcast_fee <= msg.value, "Insufficient message value"

        self._request_block_hash(
            [_origin.srcEid],  # Single target - the requesting chain
            [broadcast_fee],  # Use the decoded fee for broadcast
            0,  # Latest block
            2 * lz.default_gas_limit,  # Default gas limit x2 (read + broadcast)
            msg.value,  # covers read and broadcast
            self.default_lz_refund_address,  #fee refunds destination
        )

    else:
        # Regular message - decode and commit block hash
        block_number: uint256 = 0
        block_hash: bytes32 = empty(bytes32)
        block_number, block_hash = abi_decode(_message, (uint256, bytes32))
        self._commit_block(block_number, block_hash)

    return True
