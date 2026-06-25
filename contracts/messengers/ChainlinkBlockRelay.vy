# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title Chainlink Runtime Environment Block Relay

@notice CRE messenger for block hashes.
This contract should be deployed on multiple chains along with BlockOracle and MainnetBlockView.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""


################################################################
#                           INTERFACES                         #
################################################################

from ..modules.chainlink import IReceiver

implements: IReceiver

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

# Import CREReceiver module for cross-chain messaging
from ..modules.chainlink import CREReceiver 

initializes: CREReceiver[ownable := ownable]
exports: (
    CREReceiver.set_forwarder_address,
    CREReceiver.set_expected_author,
    CREReceiver.set_expected_workflow_name,
    CREReceiver.set_expected_workflow_id,
)
# exports: CREReceiver.__interface__

from ..modules.chainlink import CCIP
initializes: CCIP[ownable := ownable]
exports: (
    CCIP.set_router,
    CCIP.router,
    CCIP.selector_to_receiver,
    CCIP.selector_to_sender
)


################################################################
#                           CONSTANTS                          #
################################################################

MAX_N_BROADCAST: constant(uint256) = 32

################################################################
#                            STORAGE                           #
################################################################

# Block oracle
block_oracle: public(IBlockOracle)

# Structs for cached broadcast info
struct BroadcastTarget:
    chain_selector: uint64
    fee: uint256

struct BroadcastData:
    targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]
    gas_limit: uint256
    requester: address

# Broadcast targets
broadcast_data: HashMap[bytes32, BroadcastData]  # guid -> (targets: (eid, fee), gas_limit, requester)

# onReport received blocks
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
    # _forwarder_address: address,
    _ccip_router: address,
):
    """
    @notice Initialize contract with core settings
    @dev Can only be called once, assumes caller is owner, sets as delegate
    """
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)  # origin to enable createx deployment
    
    # CREReceiver.__init__(_forwarder_address)
    
    CCIP.__init__(_ccip_router)


################################################################
#                      OWNER FUNCTIONS                         #
################################################################


@external
def set_peer(_chain_selector: uint64, _peer: address):
    """
    @notice Set the receiver and the sender for cross chain transactions
    @param _chain_selector The unique CCIP destination chain selector
    @param _peer The address on the destination chain to transmit messages to and/or receive from
    """
    ownable._check_owner()

    CCIP._set_peer(_chain_selector, _peer)


@external
def set_peers(_chain_selectors: DynArray[uint64, MAX_N_BROADCAST], _peers: DynArray[address, MAX_N_BROADCAST]):
    """
    @notice Set peers for a corresponding endpoints. Batched version of OApp.setPeer that accept address (EVM only).
    @param _chain_selectors List of chain IDs
    @param _peers Addresses of the peers to be associated with the corresponding chains.
    """
    ownable._check_owner()

    assert len(_chain_selectors) == len(_peers), "Invalid peer arrays"
    for i: uint256 in range(0, len(_chain_selectors), bound=MAX_N_BROADCAST):
        CCIP._set_peer(_chain_selectors[i], _peers[i])


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
def _broadcast_block(
    _block_number: uint256,
    _block_hash: bytes32,
    _broadcast_data: BroadcastData,
):
    """
    @notice Internal function to broadcast block hash to multiple chains
    @param _block_number Block number to broadcast
    @param _block_hash Block hash to broadcast
    @param _broadcast_data Data for broadcasting
    """
    data: Bytes[64] = abi_encode(_block_number, _block_hash)
    extra_args: Bytes[68] = CCIP.build_extra_args(_broadcast_data.gas_limit)

    for target: BroadcastTarget in _broadcast_data.targets:
        # Skip if peer is not set
        receiver: address = CCIP.selector_to_receiver[target.chain_selector]
        if receiver == empty(address):
            continue

        # Send message
        message: CCIP.EVM2AnyMessage = CCIP.build_simple_message(receiver, data, extra_args)
        CCIP._transmit(target.chain_selector, message, target.fee)

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
def quote_broadcast_fees(
    _target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _ccip_receive_gas_limit: uint256,
) -> DynArray[uint256, MAX_N_BROADCAST]:
    """
    @notice Quote fees for broadcasting block hash to specified targets
    @param _target_chain_selectors List of chain selector IDs to broadcast to
    @param _ccip_receive_gas_limit Gas limit for ccipReceive
    @return Array of fees per target chain (0 if target not configured)
    """
    # Prepare dummy broadcast message (uint256 number, bytes32 hash)
    data: Bytes[64] = abi_encode(empty(uint256), empty(bytes32))

    # Prepare array of fees per chain
    fees: DynArray[uint256, MAX_N_BROADCAST] = []

    # Prepare options (same for all targets)
    extra_args: Bytes[68] = CCIP.build_extra_args(_ccip_receive_gas_limit)

    # Cycle through targets
    for selector: uint64 in _target_chain_selectors:
        receiver: address = CCIP.selector_to_receiver[selector]
        if receiver == empty(address):
            fees.append(0)
            continue

        # Get fee for target EID and append to array
        message: CCIP.EVM2AnyMessage = CCIP.build_simple_message(receiver, data, extra_args)
        fees.append(CCIP._quote(selector, message))

    return fees


@external
@payable
def broadcast_latest_block(
    _target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _ccip_receive_gas_limit: uint256,
):
    """
    @notice Broadcast latest confirmed block hash to specified chains
    @param _target_chain_selectors List of chain IDs to broadcast to
    @param _target_fees List of fees per chain (must match _target_eids length)
    @param _ccip_receive_gas_limit Gas limit for ccipReceive (same for all targets)
    @dev Only broadcast what was received via onReport to prevent potentially malicious hashes from other sources
    """

    # assert self.read_enabled, "Can only broadcast from read-enabled chains"
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    assert len(_target_chain_selectors) == len(_target_fees), "Length mismatch"

    # Get latest block from oracle
    block_number: uint256 = staticcall self.block_oracle.last_confirmed_block_number()
    block_hash: bytes32 = staticcall self.block_oracle.get_block_hash(block_number)
    assert block_hash != empty(bytes32), "No confirmed blocks"

    # Only broadcast if this block was received via lzRead
    assert self.received_blocks[block_number] == block_hash, "Unknown source"

    # Prepare broadcast targets
    broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_chain_selectors), bound=MAX_N_BROADCAST):
        broadcast_targets.append(BroadcastTarget(chain_selector=_target_chain_selectors[i], fee=_target_fees[i]))
        sum_target_fees += _target_fees[i]

    assert sum_target_fees <= msg.value, "Insufficient message value"

    self._broadcast_block(
        block_number,
        block_hash,
        BroadcastData(targets=broadcast_targets, gas_limit=_ccip_receive_gas_limit, requester=msg.sender),
    )


@external
@payable
def onReport(
    _metadata: Bytes[CREReceiver.MAX_METADATA_SIZE], 
    _report: Bytes[CREReceiver.MAX_REPORT_SIZE]
):
    """
    @notice Called by CRE Forwarder via CREReceiver after metadata validation
    @param _report The encoded message payload containing block number and hash
    """
    # Verify message source
    CREReceiver._on_report(_metadata, _report)

    # Decode block hash and number from response
    block_number: uint256 = 0
    block_hash: bytes32 = empty(bytes32)
    target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST] = []
    target_fees: DynArray[uint256, MAX_N_BROADCAST] = []
    ccip_receive_gas_limit: uint256 = 0

    block_number, block_hash, target_chain_selectors, target_fees, ccip_receive_gas_limit = abi_decode(_report, 
        (uint256, bytes32, DynArray[uint64, MAX_N_BROADCAST], DynArray[uint256, MAX_N_BROADCAST], uint256)
    )
    if block_hash == empty(bytes32):
        return  # Invalid response
    if len(target_chain_selectors) != len(target_fees):
        return  # Invalid response

    # Store received block hash
    self.received_blocks[block_number] = block_hash

    # Commit block hash to oracle
    self._commit_block(block_number, block_hash)

    if len(target_chain_selectors) > 0:
        cached_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []

        # Verify that attached value covers requested broadcast fees
        total_fee: uint256 = 0
        for i: uint256 in range(len(target_chain_selectors), bound=MAX_N_BROADCAST):
            cached_targets.append(
                BroadcastTarget(
                    chain_selector=target_chain_selectors[i], 
                    fee=target_fees[i]
                )
            )
            total_fee += target_fees[i]
        assert self.balance + msg.value >= total_fee, "Insufficient value"
        broadcast_data: BroadcastData = BroadcastData(
            targets=cached_targets,
            gas_limit=ccip_receive_gas_limit,
            requester=msg.sender
        )

        # Perform broadcast
        self._broadcast_block(
            block_number,
            block_hash,
            broadcast_data,
        )


@external
def ccipReceive(_message: CCIP.Any2EVMMessage):
    CCIP._ccipReceive(_message)

    # Regular message - decode and commit block hash
    block_number: uint256 = 0
    block_hash: bytes32 = empty(bytes32)
    block_number, block_hash = abi_decode(_message.data, (uint256, bytes32))
    self._commit_block(block_number, block_hash)


@view
@external
def supportsInterface(_interface_id: bytes4) -> bool:
    return _interface_id in CCIP.SUPPORTED_INTERFACES or _interface_id in CREReceiver.SUPPORTED_INTERFACES