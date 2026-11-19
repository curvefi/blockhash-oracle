import boa
from boa.contracts.base_evm_contract import BoaError

MAX_REFUND_GAS = 100_000
MIN_REFUND_CALL_COST = 20_000

_REFUND_WRAPPER = """
# pragma nonreentrancy on
from snekmate.auth import ownable
from contracts.modules import Funds

initializes: ownable
initializes: Funds[ownable := ownable]
exports: Funds.set_refund_gas

@deploy
def __init__():
    ownable.__init__()
    Funds.__init__()

@external
@payable
def refund(_to: address):
    Funds._refund(_to, msg.value)
"""

_GAS_ECHO_RECEIVER = """
received_gas: public(uint256)

@external
@payable
def __default__():
    self.received_gas = msg.gas
"""


def test_refund_gets_the_whole_configured_budget_whenever_it_runs():
    """The pre-check must reserve the configured refund_gas, or at its edge the recipient gets less
    and a starved refund passes for a refusal."""
    boa.env.set_balance(boa.env.eoa, 10**18)
    refunder = boa.loads(_REFUND_WRAPPER)
    refunder.set_refund_gas(MAX_REFUND_GAS, MIN_REFUND_CALL_COST)
    receiver = boa.loads(_GAS_ECHO_RECEIVER)

    def received(gas):
        with boa.env.anchor():
            refunder.refund(receiver.address, value=1, gas=gas)
            return receiver.received_gas()

    # the least caller gas the pre-check lets through
    lo, hi = 0, 5_000_000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        try:
            received(mid)
            hi = mid
        except BoaError:
            lo = mid

    assert received(hi) == received(5_000_000)
