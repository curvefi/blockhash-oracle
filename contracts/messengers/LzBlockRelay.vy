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

interface IBlockOracle:
    def commit_block(block_number: uint256, block_hash: bytes32) -> bool: nonpayable


################################################################
#                            MODULES                           #
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
    lz.nextNonce,
    lz.allowInitializePath,
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

N_CHAINS_MAX: constant(uint256) = 100
GET_BLOCKHASH_SELECTOR: constant(Bytes[4]) = method_id("get_blockhash()")
GET_BLOCKHASH_WITH_ARG_SELECTOR: constant(Bytes[4]) = method_id("get_blockhash(uint256)")

################################################################
#                            STORAGE                           #
################################################################

is_initialized: public(bool)

# Broadcast targets
broadcast_targets: public(HashMap[uint32, address])  # eid => target address
known_eids: public(DynArray[uint32, N_CHAINS_MAX])  # List of configured EIDs

# Add new struct for cached broadcast info
struct BroadcastTarget:
    eid: uint32
    fee: uint256

# Modify storage
cached_broadcast_targets: DynArray[BroadcastTarget, N_CHAINS_MAX]  # Replace simple eid array

# Read configuration
is_read_enabled: public(bool)
mainnet_eid: public(uint32)
mainnet_block_view: public(address)

# Block oracle
block_oracle: public(address)

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


event BlockHashBroadcast:
    source_eid: uint32
    block_number: uint256
    block_hash: bytes32
    targets: DynArray[BroadcastTarget, N_CHAINS_MAX]


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
def initialize(_endpoint: address, _gas_limit: uint256, _read_channel: uint32, _peer_eids: DynArray[uint32, lz.MAX_INIT_PEERS], _peers: DynArray[address, lz.MAX_INIT_PEERS]):
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

    # Initialize LayerZero module
    lz._initialize(_endpoint, _gas_limit, _read_channel, _peer_eids, _peers)

    # Set owner as delegate
    lz._set_delegate(msg.sender)


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


@internal
def _add_known_eid(_eid: uint32):
    """
    @notice Add EID to known list if not present
    """
    for existing_eid: uint32 in self.known_eids:
        if existing_eid == _eid:
            return
    self.known_eids.append(_eid)


@internal
def _remove_known_eid(_eid: uint32):
    """
    @notice Remove EID from known list
    """
    new_eids: DynArray[uint32, N_CHAINS_MAX] = []
    for existing_eid: uint32 in self.known_eids:
        if existing_eid != _eid:
            new_eids.append(existing_eid)
    self.known_eids = new_eids


@external
def add_broadcast_target(_eid: uint32, _target: address):
    """
    @notice Add a chain/contract to broadcast block hashes to
    @param _eid Chain ID to broadcast to
    @param _target Target contract address on that chain
    """
    ownable._check_owner()
    assert self.broadcast_targets[_eid] == empty(address), "Already added"
    self.broadcast_targets[_eid] = _target
    self._add_known_eid(_eid)


@external
def remove_broadcast_target(_eid: uint32):
    """
    @notice Remove a chain from broadcasting targets
    """
    ownable._check_owner()
    assert self.broadcast_targets[_eid] != empty(address), "Not a target"
    self.broadcast_targets[_eid] = empty(address)
    self._remove_known_eid(_eid)


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
    self.block_oracle = _oracle


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
def _commit_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Commit block hash to oracle
    """
    assert self.block_oracle != empty(address), "Oracle not configured"
    extcall IBlockOracle(self.block_oracle).commit_block(_block_number, _block_hash)


@view
@internal
def _prepare_read_request(_block_number: uint256) -> Bytes[lz.LZ_MESSAGE_SIZE_CAP]:
    """
    @notice Prepare complete read request message for MainnetBlockView
    @param _block_number Block number to request (0 for latest)
    @return Prepared LayerZero message bytes
    """
    # Build calldata
    calldata: Bytes[lz.LZ_READ_CALLDATA_SIZE] = empty(Bytes[lz.LZ_READ_CALLDATA_SIZE])
    if _block_number == 0:
        calldata = GET_BLOCKHASH_SELECTOR
    else:
        calldata = abi_encode(_block_number, method_id=GET_BLOCKHASH_WITH_ARG_SELECTOR)


    # Prepare read message
    return lz._prepare_read_message_bytes(
        self.mainnet_eid,
        self.mainnet_block_view,
        calldata,
        False,
        convert(block.timestamp, uint64),
        1,  # Default confirmations
    )


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@view
@external
def quote_read_fee(_block_number: uint256 = 0, _gas_limit: uint256 = 0, _value: uint256 = 0, _data_size: uint32 = 64) -> uint256:
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
        lz.LZ_READ_CHANNEL, empty(address), message, _gas_limit, _value, _data_size  # Expected response size
    )


@view
@external
def quote_broadcast_fees(
    _target_eids: DynArray[uint32, N_CHAINS_MAX], _gas_limit: uint256 = 0
) -> DynArray[uint256, N_CHAINS_MAX]:
    """
    @notice Quote fees for broadcasting block hash to specified targets
    @param _target_eids List of chain IDs to broadcast to
    @param _gas_limit Optional gas limit override
    @return Array of fees per target chain (0 if target not configured)
    """
    # Prepare dummy broadcast message (uint256 number, bytes32 hash)
    message: Bytes[lz.LZ_MESSAGE_SIZE_CAP] = abi_encode(empty(uint256), empty(bytes32))

    # Get fees per chain
    fees: DynArray[uint256, N_CHAINS_MAX] = []

    for eid: uint32 in _target_eids:
        target: address = self.broadcast_targets[eid]
        if target == empty(address):
            fees.append(0)
            continue

        fee: uint256 = lz._quote_lz_fee(eid, target, message, _gas_limit)
        fees.append(fee)

    return fees


@payable
@external
def request_block_hash(
    _target_eids: DynArray[uint32, N_CHAINS_MAX],
    _target_fees: DynArray[uint256, N_CHAINS_MAX],  # Add fees array parameter
    _block_number: uint256 = 0,
    _gas_limit: uint256 = 0
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
    assert self.is_read_enabled, "Read not enabled - call set_read_config"
    assert self.mainnet_block_view != empty(address), "Mainnet view not set - call set_read_config"
    assert len(_target_eids) == len(_target_fees), "Length mismatch"

    # Cache target EIDs and fees for lzReceive
    cached_targets: DynArray[BroadcastTarget, N_CHAINS_MAX] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_eids), bound=N_CHAINS_MAX):
        cached_targets.append(BroadcastTarget(
            eid = _target_eids[i],
            fee = _target_fees[i]
        ))
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
        msg.value,  # _request_msg_value: Use cached fee as send message value
        msg.sender,  # _refund_address: Refund unspent fees to read requestor
        False  # _perform_fee_check: No fee check
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
    @notice Handle both regular messages and read responses
    @dev Receives block hashes either from mainnet read or from broadcast
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


        # First commit locally
        self._commit_block(block_number, block_hash)

        # Get cached targets and broadcast if we have any
        broadcast_targets: DynArray[BroadcastTarget, N_CHAINS_MAX] = self.cached_broadcast_targets
        if len(broadcast_targets) > 0:
            for target: BroadcastTarget in broadcast_targets:
                target_address: address = self.broadcast_targets[target.eid]
                if target_address == empty(address):
                    continue
                lz._send_message(
                    target.eid,  # _dstEid
                    convert(target_address, bytes32),  # _receiver
                    _message,  # _message
                    0,  # _gas_limit: Use default gas limit
                    0,  # _lz_receive_value: No value to attach to receive call
                    0,  # _data_size: Zero data size (not a read)
                    target.fee,  # _request_msg_value: Use cached fee as send message value
                    self,  # _refund_address: shouldn't refund executor (can call withdraw_eth later)
                    False,  # _perform_fee_check: No fee check
                )

            # Clear cache after broadcasting
            self.cached_broadcast_targets = empty(DynArray[BroadcastTarget, N_CHAINS_MAX])

            # Extract eids for event
            log BlockHashBroadcast(_origin.srcEid, block_number, block_hash, broadcast_targets)
    else:
        # Regular message - decode and commit block hash
        block_number: uint256 = 0
        block_hash: bytes32 = empty(bytes32)
        block_number, block_hash = abi_decode(_message, (uint256, bytes32))
        self._commit_block(block_number, block_hash)

    return True
