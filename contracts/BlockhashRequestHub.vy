# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title Blockhash Request Hub

@notice Permissionless entry point for pulling a mainnet block hash onto sidechains. One payable call
drives either or both rails: LayerZero synchronously via LZBlockRelay.request_block_hash, and
Chainlink CRE by funding ChainlinkBlockRelay with the CCIP fees and emitting the log that triggers
the CRE workflow.

A satellite: needs no change to either relay, and is redeployed by re-pointing the workflow trigger.
Fees are not refunded past the quote.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi

"""


################################################################
#                           INTERFACES                         #
################################################################

from ethereum.ercs import IERC20

# Imported for their interfaces, so a relay signature change breaks this contract's compilation
from . import BlockOracle
from .messengers import ChainlinkBlockRelay
from .messengers import LZBlockRelay


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


################################################################
#                           CONSTANTS                          #
################################################################

MAX_N_BROADCAST: constant(uint256) = 32  # must match both relays

RAIL_LZ: public(constant(uint8)) = 1
RAIL_CRE: public(constant(uint8)) = 2

BPS: constant(uint256) = 10_000


################################################################
#                            STORAGE                           #
################################################################

block_oracle: public(BlockOracle.__interface__)

# Delivery rails; empty address disables the rail
lz_relay: public(LZBlockRelay.__interface__)
cre_relay: public(ChainlinkBlockRelay.__interface__)

# Pricing
base_fee: public(uint256)  # flat charge per CRE request, covers one workflow execution
fee_per_target: public(uint256)  # added per CCIP target, tracks onReport's per-send gas
fee_multiplier_bps: public(uint256)  # headroom on CCIP quotes, they drift before onReport fires

# Gas the workflow forwards into onReport; on-chain so it retunes without a workflow redeploy
base_on_report_gas: public(uint256)
ccip_send_gas: public(uint256)

nonce: public(uint256)


################################################################
#                            EVENTS                            #
################################################################

event CREBlockhashRequested:
    request_id: indexed(bytes32)
    requester: indexed(address)
    block_number: uint256
    chain_selectors: DynArray[uint64, MAX_N_BROADCAST]
    max_fees: DynArray[uint256, MAX_N_BROADCAST]
    ccip_receive_gas_limit: uint256
    on_report_gas_limit: uint256

event LZBlockhashRequested:
    request_id: indexed(bytes32)
    requester: indexed(address)
    block_number: uint256
    target_eids: DynArray[uint32, MAX_N_BROADCAST]
    target_fees: DynArray[uint256, MAX_N_BROADCAST]

event SetRelays:
    lz_relay: indexed(address)
    cre_relay: indexed(address)

event SetFees:
    base_fee: uint256
    fee_per_target: uint256
    fee_multiplier_bps: uint256

event SetGasParams:
    base_on_report_gas: uint256
    ccip_send_gas: uint256

################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__(
    _block_oracle: address,
    _lz_relay: address,
    _cre_relay: address,
    _base_fee: uint256,
    _fee_per_target: uint256,
    _fee_multiplier_bps: uint256,
    _base_on_report_gas: uint256,
    _ccip_send_gas: uint256,
):
    """
    @notice Initialize the hub
    @dev The oracle is fixed at deploy; redeploy the hub to move it
    @param _lz_relay LayerZero relay, empty to ship with that rail disabled
    @param _cre_relay Chainlink relay, empty to ship with that rail disabled
    @param _fee_multiplier_bps Headroom on CCIP quotes, in bps; must be at least 10_000
    """
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)  # origin to enable createx deployment

    assert _block_oracle != empty(address), "Oracle not set"
    assert _fee_multiplier_bps >= BPS, "Multiplier below 100%"

    self.block_oracle = BlockOracle.__interface__(_block_oracle)
    self._set_relays(_lz_relay, _cre_relay)

    self.base_fee = _base_fee
    self.fee_per_target = _fee_per_target
    self.fee_multiplier_bps = _fee_multiplier_bps
    self.base_on_report_gas = _base_on_report_gas
    self.ccip_send_gas = _ccip_send_gas

    log SetFees(
        base_fee=_base_fee, fee_per_target=_fee_per_target, fee_multiplier_bps=_fee_multiplier_bps
    )
    log SetGasParams(base_on_report_gas=_base_on_report_gas, ccip_send_gas=_ccip_send_gas)


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
def _set_relays(_lz_relay: address, _cre_relay: address):
    """
    @dev A relay that is not a committer can never make a request land, so refuse to point at one
    """
    oracle: BlockOracle.__interface__ = self.block_oracle
    if _lz_relay != empty(address):
        assert staticcall oracle.is_committer(_lz_relay), "LZ relay not a committer"
    if _cre_relay != empty(address):
        assert staticcall oracle.is_committer(_cre_relay), "CRE relay not a committer"

    self.lz_relay = LZBlockRelay.__interface__(_lz_relay)
    self.cre_relay = ChainlinkBlockRelay.__interface__(_cre_relay)
    log SetRelays(lz_relay=_lz_relay, cre_relay=_cre_relay)


@internal
@view
def _sum(_values: DynArray[uint256, MAX_N_BROADCAST]) -> uint256:
    total: uint256 = 0
    for value: uint256 in _values:
        total += value
    return total


@internal
@view
def _lz_fees(
    _eids: DynArray[uint32, MAX_N_BROADCAST], _lz_gas: uint128
) -> DynArray[uint256, MAX_N_BROADCAST]:
    """
    @dev The relay quotes 0 for a target it cannot reach, so this doubles as a peer check
    """
    assert len(_eids) > 0, "No targets"
    fees: DynArray[uint256, MAX_N_BROADCAST] = staticcall self.lz_relay.quote_broadcast_fees(
        _eids, _lz_gas
    )
    for fee: uint256 in fees:
        assert fee != 0, "No LayerZero route"
    return fees


@internal
@view
def _ccip_max_fees(
    _selectors: DynArray[uint64, MAX_N_BROADCAST], _ccip_gas: uint256
) -> DynArray[uint256, MAX_N_BROADCAST]:
    """
    @dev max_fee is a cap, not a payment: CCIP._transmit re-quotes and forwards only the real fee,
         so headroom costs nothing unless fees rise between request and onReport
    """
    assert len(_selectors) > 0, "No targets"
    quotes: DynArray[uint256, MAX_N_BROADCAST] = staticcall self.cre_relay.quote_broadcast_fees(
        _selectors, _ccip_gas
    )
    multiplier: uint256 = self.fee_multiplier_bps
    max_fees: DynArray[uint256, MAX_N_BROADCAST] = []
    for quote: uint256 in quotes:
        assert quote != 0, "No CCIP route"
        max_fees.append(quote * multiplier // BPS)
    return max_fees


@internal
@view
def _surcharge(_n_targets: uint256) -> uint256:
    return self.base_fee + _n_targets * self.fee_per_target


################################################################
#                       ADMIN FUNCTIONS                        #
################################################################

@external
def set_relays(_lz_relay: address, _cre_relay: address):
    """
    @notice Point the hub at the delivery relays; empty address disables that rail
    """
    ownable._check_owner()
    self._set_relays(_lz_relay, _cre_relay)


@external
def set_fees(_base_fee: uint256, _fee_per_target: uint256, _fee_multiplier_bps: uint256):
    """
    @notice Update pricing
    @dev The surcharge is a spam price, not cost recovery; erring high is the cheap direction
    """
    ownable._check_owner()
    assert _fee_multiplier_bps >= BPS, "Multiplier below 100%"

    self.base_fee = _base_fee
    self.fee_per_target = _fee_per_target
    self.fee_multiplier_bps = _fee_multiplier_bps
    log SetFees(
        base_fee=_base_fee, fee_per_target=_fee_per_target, fee_multiplier_bps=_fee_multiplier_bps
    )


@external
def set_gas_params(_base_on_report_gas: uint256, _ccip_send_gas: uint256):
    """
    @notice Retune the gas the workflow forwards into onReport
    @dev Under-estimating strands a request: writeReport runs out of gas after fees were pushed
    """
    ownable._check_owner()

    self.base_on_report_gas = _base_on_report_gas
    self.ccip_send_gas = _ccip_send_gas
    log SetGasParams(base_on_report_gas=_base_on_report_gas, ccip_send_gas=_ccip_send_gas)


@external
def withdraw_eth(_amount: uint256):
    """
    @notice Withdraw ETH from contract
    @dev Surcharges accrue here; CCIP fees do not, they are pushed to the relay on request
    """
    ownable._check_owner()

    assert self.balance >= _amount, "Insufficient balance"
    send(msg.sender, _amount)


@external
def recover_erc20(_token: address, _to: address, _amount: uint256):
    """
    @notice Recover ERC20 tokens sent to this contract
    @dev The hub deals only in native token; a direct transfer can still land here
    """
    ownable._check_owner()

    assert extcall IERC20(_token).transfer(_to, _amount), "Transfer failed"


################################################################
#                     EXTERNAL FUNCTIONS                       #
################################################################

@external
@payable
@reentrant
def __default__():
    """
    @notice Receive ETH: LayerZero fee refunds and direct funding
    """
    pass


@external
@view
def quote_request(
    _rails: uint8,
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _ccip_gas: uint256,
    _lz_gas: uint128,
    _read_gas: uint128,
) -> (uint256, uint256, uint256, uint256):
    """
    @notice Quote a request before sending it
    @return (LayerZero total, CCIP total, surcharge, sum of the three)
    """
    lz_total: uint256 = 0
    ccip_total: uint256 = 0
    surcharge: uint256 = 0

    if _rails & RAIL_LZ != 0:
        # quote_read_fee already covers the value carried back for the broadcasts
        lz_total = staticcall self.lz_relay.quote_read_fee(
            _read_gas, convert(self._sum(self._lz_fees(_target_eids, _lz_gas)), uint128)
        )

    if _rails & RAIL_CRE != 0:
        ccip_total = self._sum(self._ccip_max_fees(_target_selectors, _ccip_gas))
        surcharge = self._surcharge(len(_target_selectors))

    return lz_total, ccip_total, surcharge, lz_total + ccip_total + surcharge


@external
@payable
def request(
    _rails: uint8,
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _block_number: uint256,
    _ccip_gas: uint256,
    _lz_gas: uint128,
    _read_gas: uint128,
) -> bytes32:
    """
    @notice Request a mainnet block hash be delivered to the given targets
    @dev The LayerZero leg completes synchronously; the Chainlink leg finishes when the workflow
         answers the emitted log. Quote with quote_request first: only the excess comes back.
    @param _rails Bitfield of RAIL_LZ and RAIL_CRE; at least one must be set
    @param _target_eids LayerZero endpoint ids, used only by the LayerZero rail
    @param _target_selectors CCIP chain selectors, used only by the Chainlink rail
    @param _block_number Block to fetch, and the value both rails vote with. Unchecked beyond being
                         non-zero: MainnetBlockView serves [head - 8192, head - 64] and both rails
                         resolve later than this call, which only makes the block older, so pick with
                         room to spare - head - 100 is comfortable.
    @param _ccip_gas Gas limit for ccipReceive on each CCIP target
    @param _lz_gas Gas limit for lzReceive on each LayerZero target
    @param _read_gas Gas limit for the lzRead return message
    @return Request id, for correlating the emitted logs with delivery
    """
    assert _rails & (RAIL_LZ | RAIL_CRE) != 0, "No rail selected"
    # Pinned, so both rails vote on the same number; the oracle counts votes per (number, hash)
    assert _block_number != 0, "No block number"

    nonce: uint256 = self.nonce + 1
    self.nonce = nonce
    request_id: bytes32 = keccak256(abi_encode(chain.id, self, nonce))

    spent: uint256 = 0

    # ── LayerZero: synchronous, the relay reads and broadcasts on its own ──
    if _rails & RAIL_LZ != 0:
        assert self.lz_relay.address != empty(address), "LayerZero rail disabled"

        fees: DynArray[uint256, MAX_N_BROADCAST] = self._lz_fees(_target_eids, _lz_gas)
        lz_total: uint256 = staticcall self.lz_relay.quote_read_fee(
            _read_gas, convert(self._sum(fees), uint128)
        )
        spent += lz_total
        assert msg.value >= spent, "Insufficient value"

        # Quoted in this transaction, so no headroom; endpoint dust comes back and is swept
        extcall self.lz_relay.request_block_hash(
            _target_eids, fees, _lz_gas, _read_gas, _block_number, value=lz_total
        )
        log LZBlockhashRequested(
            request_id=request_id,
            requester=msg.sender,
            block_number=_block_number,
            target_eids=_target_eids,
            target_fees=fees,
        )

    # ── Chainlink CRE: fund the relay, then emit the workflow's trigger ──
    if _rails & RAIL_CRE != 0:
        assert self.cre_relay.address != empty(address), "CRE rail disabled"

        max_fees: DynArray[uint256, MAX_N_BROADCAST] = self._ccip_max_fees(
            _target_selectors, _ccip_gas
        )
        ccip_total: uint256 = self._sum(max_fees)

        spent += ccip_total + self._surcharge(len(_target_selectors))
        assert msg.value >= spent, "Insufficient value"

        # onReport spends CCIP fees from the relay's own balance, so fund it before the report.
        # raw_call not send: the relay's default is reentrant, 2300 gas is not worth relying on.
        raw_call(self.cre_relay.address, b"", value=ccip_total)

        log CREBlockhashRequested(
            request_id=request_id,
            requester=msg.sender,
            block_number=_block_number,
            chain_selectors=_target_selectors,
            max_fees=max_fees,
            ccip_receive_gas_limit=_ccip_gas,
            on_report_gas_limit=self.base_on_report_gas
            + len(_target_selectors) * self.ccip_send_gas,
        )

    # Overpayment is returned, the quote is not. Non-fatal: a caller that cannot receive ETH has no
    # exact amount it could safely send, since quotes drift.
    if msg.value > spent:
        returned: bool = raw_call(
            msg.sender, b"", value=msg.value - spent, revert_on_failure=False
        )

    return request_id
