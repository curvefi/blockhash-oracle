# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title Chainlink CRE + CCIP Block Relay

@notice Block-hash messenger over Chainlink CRE (inbound reports) and CCIP (cross-chain fanout/receive).
This contract should be deployed on multiple chains along with BlockOracle and MainnetBlockView.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""


################################################################
#                           INTERFACES                         #
################################################################

from ..modules.chainlink.src import IReceiver
from ethereum.ercs import IERC20

implements: IReceiver

interface IBlockOracle:
    def commit_block(block_number: uint256, block_hash: bytes32) -> bool: nonpayable
    def last_confirmed_block_number() -> uint256: view
    def get_block_hash(block_number: uint256) -> bytes32: view
    def committer_votes(committer: address, block_number: uint256) -> bytes32: view


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
from ..modules.chainlink.src import CREReceiver

initializes: CREReceiver[ownable := ownable]
exports: (
    CREReceiver.set_forwarder_address,
    CREReceiver.set_expected_author,
    CREReceiver.set_expected_workflow_name,
    CREReceiver.set_expected_workflow_id,
    CREReceiver.forwarder_address,
    CREReceiver.expected_author,
    CREReceiver.expected_workflow_name,
    CREReceiver.expected_workflow_id,
)
# exports: CREReceiver.__interface__

from ..modules.chainlink.src import CCIP
initializes: CCIP[ownable := ownable]
exports: (
    CCIP.set_router,
    CCIP.router,
    CCIP.selector_to_receiver,
    CCIP.selector_to_sender,
    CCIP.set_peer,
    CCIP.set_sender,
    CCIP.set_receiver,
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
    max_fee: uint256

struct BroadcastData:
    targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]
    gas_limit: uint256
    requester: address

# onReport received blocks
received_blocks: HashMap[uint256, bytes32]  # block_number -> block_hash

################################################################
#                            EVENTS                            #
################################################################

event BlockHashBroadcast:
    block_number: indexed(uint256)
    block_hash: indexed(bytes32)
    targets: DynArray[BroadcastTarget, MAX_N_BROADCAST]

event SetBlockOracle:
    oracle: indexed(address)

event MessageSent:
    message_id: bytes32
    chain_selector: uint64
    receiver: address
    block_number: indexed(uint256)
    block_hash: indexed(bytes32)
    fee: uint256

event RefundFailed:
    requester: indexed(address)
    amount: uint256


################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__(
    _ccip_router: address,
    _forwarder_address: address,
):
    """
    @notice Initialize contract with core settings
    @dev Can only be called once, assumes caller is owner, sets as delegate
    @dev Set _forwarder_address empty to disable CRE
    """
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)  # origin to enable createx deployment

    CREReceiver.__init__(_forwarder_address)

    CCIP.__init__(_ccip_router)


################################################################
#                      OWNER FUNCTIONS                         #
################################################################


@external
def set_peers(_chain_selectors: DynArray[uint64, MAX_N_BROADCAST], _peers: DynArray[address, MAX_N_BROADCAST]):
    """
    @notice Set peers for corresponding chain selectors. Batched version of CCIP.set_peer (EVM only).
    @param _chain_selectors List of CCIP chain selectors
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
    log SetBlockOracle(oracle=_oracle)


@external
def withdraw_eth(_amount: uint256):
    """
    @notice Withdraw ETH from contract
    @dev ETH can be accumulated from unused CCIP fees
    @param _amount Amount to withdraw
    """
    ownable._check_owner()

    assert self.balance >= _amount, "Insufficient balance"
    # raw_call, not send: a multisig or agent owner needs more than send's 2300-gas stipend
    raw_call(msg.sender, b"", value=_amount)


@external
def recover_erc20(_token: address, _to: address, _amount: uint256):
    """
    @notice Recover ERC20 tokens sent to this contract
    @dev Data-only relay: token-bearing CCIP messages are rejected, but a direct transfer can still land here
    """
    ownable._check_owner()

    assert extcall IERC20(_token).transfer(_to, _amount), "Transfer failed"


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################


@internal
def _commit_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Commit block hash to oracle
    """
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    # Skip if block already applied with the same hash
    applied_blockhash: bytes32 = staticcall self.block_oracle.get_block_hash(_block_number)
    if applied_blockhash == _block_hash:
        return
    assert applied_blockhash == empty(bytes32), "Different blockhash already applied"
    # Skip a vote this relay already cast; if a lowered threshold now suffices, apply_block is permissionless
    if staticcall self.block_oracle.committer_votes(self, _block_number) == _block_hash:
        return
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
    extra_args: Bytes[68] = CCIP._build_extra_args(_broadcast_data.gas_limit)
    successful_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    unused_fees: uint256 = 0

    for target: BroadcastTarget in _broadcast_data.targets:
        # Skip if peer is not set; its fee goes back with the rest of the change
        receiver: address = CCIP.selector_to_receiver[target.chain_selector]
        if receiver == empty(address):
            unused_fees += target.max_fee
            continue

        # Send message
        message: CCIP.EVM2AnyMessage = CCIP._build_simple_message(target.chain_selector, data, extra_args)
        message_id: bytes32 = empty(bytes32)
        fee: uint256 = 0
        message_id, fee = CCIP._transmit(target.chain_selector, message, target.max_fee)
        unused_fees += target.max_fee - fee
        log MessageSent(
            message_id=message_id,
            chain_selector=target.chain_selector,
            receiver=receiver,
            block_number=_block_number,
            block_hash=_block_hash,
            fee=fee,
        )
        successful_targets.append(target)

    # Refund unused fee to a direct (public) requester; CRE path keeps it in the treasury.
    # Non-fatal: a caller that cannot take the change still gets its broadcast, and the ETH stays
    # in the treasury (owner-withdrawable). raw_call, not send: send's stipend (none at all on a
    # zero refund) failed every contract caller.
    if _broadcast_data.requester != empty(address) and unused_fees > 0:
        if not raw_call(_broadcast_data.requester, b"", value=unused_fees, revert_on_failure=False):
            log RefundFailed(requester=_broadcast_data.requester, amount=unused_fees)
    log BlockHashBroadcast(
        block_number=_block_number,
        block_hash=_block_hash,
        targets=successful_targets,
    )


@view
@internal
def _latest_block_number() -> uint256:
    """
    @notice The oracle's latest confirmed block, checking the oracle is set before calling it
    """
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    return staticcall self.block_oracle.last_confirmed_block_number()


@internal
def _broadcast_confirmed(
    _block_number: uint256,
    _target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _ccip_receive_gas_limit: uint256,
    _value: uint256,
):
    """
    @notice Broadcast a confirmed block this relay received itself, fees paid by the caller
    @dev Only broadcast what was received via onReport to prevent potentially malicious hashes from other sources
    """
    assert self.block_oracle != empty(IBlockOracle), "Oracle not configured"
    assert len(_target_chain_selectors) == len(_target_fees), "Length mismatch"

    block_hash: bytes32 = staticcall self.block_oracle.get_block_hash(_block_number)
    assert block_hash != empty(bytes32), "Block not confirmed"

    # Only broadcast if this block was received via onReport
    assert self.received_blocks[_block_number] == block_hash, "Unknown source"

    # Prepare broadcast targets
    broadcast_targets: DynArray[BroadcastTarget, MAX_N_BROADCAST] = []
    sum_target_fees: uint256 = 0
    for i: uint256 in range(0, len(_target_chain_selectors), bound=MAX_N_BROADCAST):
        broadcast_targets.append(BroadcastTarget(chain_selector=_target_chain_selectors[i], max_fee=_target_fees[i]))
        sum_target_fees += _target_fees[i]

    assert sum_target_fees == _value, "Insufficient message value"

    self._broadcast_block(
        _block_number,
        block_hash,
        BroadcastData(targets=broadcast_targets, gas_limit=_ccip_receive_gas_limit, requester=msg.sender),
    )


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@external
@payable
@reentrant
def __default__():
    """
    @notice Receive ETH: treasury funding and public overpayment
    @dev CCIP does not refund Router overpayment, so any surplus accrues here (owner-withdrawable)
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
    extra_args: Bytes[68] = CCIP._build_extra_args(_ccip_receive_gas_limit)

    # Cycle through targets
    for selector: uint64 in _target_chain_selectors:
        receiver: address = CCIP.selector_to_receiver[selector]
        if receiver == empty(address):
            fees.append(0)
            continue

        # Get fee for target chain selector and append to array
        message: CCIP.EVM2AnyMessage = CCIP._build_simple_message(selector, data, extra_args)
        fees.append(CCIP._quote(selector, message, True))  # allow_unsupported

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
    @param _target_chain_selectors List of CCIP chain selectors to broadcast to
    @param _target_fees List of fees per chain (must match _target_chain_selectors length)
    @param _ccip_receive_gas_limit Gas limit for ccipReceive (same for all targets)
    @dev Reverts if another source confirmed the oracle's latest block; use broadcast_block then
    """
    self._broadcast_confirmed(
        self._latest_block_number(),
        _target_chain_selectors,
        _target_fees,
        _ccip_receive_gas_limit,
        msg.value,
    )


@external
@payable
def broadcast_block(
    _block_number: uint256,
    _target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _ccip_receive_gas_limit: uint256,
):
    """
    @notice Broadcast a confirmed block this relay received to specified chains
    @param _block_number Block to broadcast; any confirmed block received via onReport, not only the latest
    @param _target_chain_selectors List of CCIP chain selectors to broadcast to
    @param _target_fees List of fees per chain (must match _target_chain_selectors length)
    @param _ccip_receive_gas_limit Gas limit for ccipReceive (same for all targets)
    @dev A newer block confirmed by another source must not stop rebroadcasting the ones this relay received
    """
    self._broadcast_confirmed(
        _block_number, _target_chain_selectors, _target_fees, _ccip_receive_gas_limit, msg.value
    )


@external
def onReport(
    _metadata: Bytes[CREReceiver.MAX_METADATA_SIZE],
    _report: Bytes[CREReceiver.MAX_REPORT_SIZE]
):
    """
    @notice Called by the CRE Forwarder; authenticates the report via CREReceiver (strict mode)
            before decoding it
    @param _report ABI-encoded (relay, chain id, block number, block hash, target selectors,
           target fees, ccip receive gas limit)
    """
    # Strict mode (default): reverts until a workflow id or author is configured.
    # Never pass strict_mode=False in production, it accepts any workflow on the forwarder.
    CREReceiver._on_report(_metadata, _report)

    # Decode block hash and number from response
    relay: address = empty(address)
    chain_id: uint256 = 0
    block_number: uint256 = 0
    block_hash: bytes32 = empty(bytes32)
    target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST] = []
    target_fees: DynArray[uint256, MAX_N_BROADCAST] = []
    ccip_receive_gas_limit: uint256 = 0

    relay, chain_id, block_number, block_hash, target_chain_selectors, target_fees, ccip_receive_gas_limit = abi_decode(_report,
        (address, uint256, uint256, bytes32, DynArray[uint64, MAX_N_BROADCAST], DynArray[uint256, MAX_N_BROADCAST], uint256)
    )
    # The forwarder does not sign the receiver, so the report names its own destination
    assert relay == self and chain_id == chain.id, "Wrong destination"
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
                    max_fee=target_fees[i]
                )
            )
            total_fee += target_fees[i]
        assert self.balance >= total_fee, "Insufficient value"
        broadcast_data: BroadcastData = BroadcastData(
            targets=cached_targets,
            gas_limit=ccip_receive_gas_limit,
            requester=empty(address)  # CRE path: no refund, unused fee stays in treasury
        )

        # Perform broadcast
        self._broadcast_block(
            block_number,
            block_hash,
            broadcast_data,
        )


# Every destination gets one shared gas limit for this call, sized from per-chain measurements:
# README "CCIP receive gas limit". Re-run scripts/ccip_gas_probe.py if this path changes.
@external
def ccipReceive(_message: CCIP.Any2EVMMessage):
    CCIP._ccipReceive(_message)
    assert len(_message.dest_token_amounts) == 0, "No tokens"

    # Regular message - decode and commit block hash
    block_number: uint256 = 0
    block_hash: bytes32 = empty(bytes32)
    block_number, block_hash = abi_decode(_message.data, (uint256, bytes32))
    if block_hash == empty(bytes32):
        return  # Invalid response
    self._commit_block(block_number, block_hash)


@view
@external
def supportsInterface(_interface_id: bytes4) -> bool:
    return _interface_id in CCIP.SUPPORTED_INTERFACES or _interface_id in CREReceiver.SUPPORTED_INTERFACES
