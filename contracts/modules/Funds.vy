# pragma version 0.4.3
# pragma optimize gas
# pragma nonreentrancy on

"""
@title Funds - ETH change refunds and the owner's withdrawals

@notice Refunds get a fixed, owner-tunable gas budget, so whoever submits the transaction cannot
starve them; a recipient that refuses one is logged, not reverted on

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

from ethereum.ercs import IERC20
from snekmate.auth import ownable

uses: ownable


################################################################
#                            EVENTS                            #
################################################################

event SetRefundGas:
    refund_gas: uint256
    call_cost: uint256

event RefundFailed:
    requester: indexed(address)
    amount: uint256


################################################################
#                           CONSTANTS                          #
################################################################

INITIAL_REFUND_GAS: constant(uint256) = 50_000
# Far below the CRE forwarder's ~160k routing minimum, so a refund callback cannot route a
# pending report into the relay's lock
MAX_REFUND_GAS: constant(uint256) = 100_000
# The value call's own cost beyond its gas, Monad's cold access included; lower lets a refund
# start short of its gas
MIN_REFUND_CALL_COST: constant(uint256) = 20_000


################################################################
#                            STORAGE                           #
################################################################

# On-chain so they retune without a redeploy
refund_gas: public(uint256)
refund_call_cost: public(uint256)


################################################################
#                          CONSTRUCTOR                         #
################################################################

@deploy
def __init__():
    self.refund_gas = INITIAL_REFUND_GAS
    self.refund_call_cost = MIN_REFUND_CALL_COST


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def set_refund_gas(_refund_gas: uint256, _call_cost: uint256):
    """
    @notice Set the gas each refund gets, and that call's own cost beyond it
    @dev Raising either raises the gas a refunding call needs, and pending LZ read responses keep
         the gas fixed at request: raise the read gas first and let them land
    """
    ownable._check_owner()

    assert _refund_gas <= MAX_REFUND_GAS, "Refund gas too high"
    assert _call_cost >= MIN_REFUND_CALL_COST, "Call cost too low"
    self.refund_gas = _refund_gas
    self.refund_call_cost = _call_cost
    log SetRefundGas(refund_gas=_refund_gas, call_cost=_call_cost)


@external
def withdraw_eth(_amount: uint256):
    """
    @notice Withdraw ETH from contract
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
    @dev These contracts deal only in native token; a direct transfer can still land here
    @param _token ERC20 token to recover
    @param _to Recipient of the tokens
    @param _amount Amount to transfer
    """
    ownable._check_owner()

    # default_return_value: tokens that return nothing on a successful transfer (USDT) are recoverable
    assert extcall IERC20(_token).transfer(
        _to, _amount, default_return_value=True
    ), "Transfer failed"


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
def _refund(_requester: address, _amount: uint256):
    """
    @notice Send _amount to _requester with exactly refund_gas, logging if it refuses
    @dev Reverts rather than starve the recipient, which would read as a refusal
    """
    refund_gas: uint256 = self.refund_gas
    # EIP-150 keeps 1/64 back
    assert msg.gas > refund_gas * 64 // 63 + self.refund_call_cost, "Not enough gas to refund"
    if not raw_call(_requester, b"", value=_amount, gas=refund_gas, revert_on_failure=False):
        log RefundFailed(requester=_requester, amount=_amount)
