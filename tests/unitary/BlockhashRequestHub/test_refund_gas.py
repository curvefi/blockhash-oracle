import boa

from conftest import (
    CCIP_RECEIVE_GAS_LIMIT,
    INITIAL_REFUND_GAS,
    LZ_ONE,
    LZ_READ_GAS_LIMIT,
    LZ_RECEIVE_GAS_LIMIT,
    MAX_REFUND_GAS,
    MIN_REFUND_CALL_COST,
    PINNED_BLOCK,
    RAIL_LZ,
    RECEIVE_ROUNDS_OVER_INITIAL_REFUND,
    lz_cost,
)

CONTRACT_CALLER = "tests/mocks/ContractCaller.vy"


def _request_data(hub):
    return hub.request.prepare_calldata(
        RAIL_LZ,
        LZ_ONE,
        [],
        PINNED_BLOCK,
        CCIP_RECEIVE_GAS_LIMIT,
        LZ_RECEIVE_GAS_LIMIT,
        LZ_READ_GAS_LIMIT,
    )


def test_set_refund_gas(hub, dev_deployer):
    """Starts at the measured values; only the owner retunes it, within the cap and the floor."""
    assert hub.refund_gas() == INITIAL_REFUND_GAS
    assert hub.refund_call_cost() == MIN_REFUND_CALL_COST

    with boa.env.prank(boa.env.generate_address()):
        with boa.reverts("ownable: caller is not the owner"):
            hub.set_refund_gas(MAX_REFUND_GAS, MIN_REFUND_CALL_COST)

    with boa.env.prank(dev_deployer):
        with boa.reverts("Refund gas too high"):
            hub.set_refund_gas(MAX_REFUND_GAS + 1, MIN_REFUND_CALL_COST)
        with boa.reverts("Call cost too low"):
            hub.set_refund_gas(MAX_REFUND_GAS, MIN_REFUND_CALL_COST - 1)
        hub.set_refund_gas(MAX_REFUND_GAS, MIN_REFUND_CALL_COST + 1)

    events = hub.get_logs()
    assert hub.refund_gas() == MAX_REFUND_GAS
    assert hub.refund_call_cost() == MIN_REFUND_CALL_COST + 1
    assert any(type(e).__name__ == "SetRefundGas" for e in events)


def test_refund_gets_the_configured_gas(hub, mock_lz_relay, dev_deployer):
    """The refund gets refund_gas and checks for refund_call_cost, not compiled-in figures."""
    caller = boa.load(CONTRACT_CALLER, True)
    caller.set_burn_rounds(RECEIVE_ROUNDS_OVER_INITIAL_REFUND)
    boa.env.set_balance(caller.address, lz_cost(1) + 10**17)
    data = _request_data(hub)

    def received():
        with boa.env.anchor():
            with boa.env.prank(caller.address):
                caller.execute(hub.address, data, value=lz_cost(1) + 10**17, gas=1_000_000)
            return caller.received()

    assert received() == 0  # the initial budget is too little for this receiver
    with boa.env.prank(dev_deployer):
        hub.set_refund_gas(MAX_REFUND_GAS, MIN_REFUND_CALL_COST)
    assert received() == 10**17

    with boa.env.prank(dev_deployer):
        hub.set_refund_gas(MAX_REFUND_GAS, 1_000_000)
    with boa.reverts("Not enough gas to refund"):
        received()
