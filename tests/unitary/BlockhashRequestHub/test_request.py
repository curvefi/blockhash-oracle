import boa

from conftest import (
    ARBITRUM_EID,
    BASE_EID,
    BASE_ON_REPORT_GAS,
    CCIP_ONE,
    CCIP_RECEIVE_GAS_LIMIT,
    CCIP_SEND_GAS,
    CCIP_TWO,
    KAVA_EID,
    LZ_ONE,
    LZ_READ_GAS_LIMIT,
    LZ_RECEIVE_GAS_LIMIT,
    LZ_TWO,
    PINNED_BLOCK,
    RAIL_BOTH,
    RAIL_CRE,
    RAIL_LZ,
    ccip_max_fee,
    cre_cost,
    lz_cost,
    surcharge,
)


def _request(hub, caller, rails, eids, selectors, value, block_number=PINNED_BLOCK):
    with boa.env.prank(caller):
        return hub.request(
            rails,
            eids,
            selectors,
            block_number,
            CCIP_RECEIVE_GAS_LIMIT,
            LZ_RECEIVE_GAS_LIMIT,
            LZ_READ_GAS_LIMIT,
            value=value,
        )


def _event(hub, name):
    return next(e for e in hub.get_logs() if type(e).__name__ == name)


def test_lz_request_forwards_targets_and_pinned_block(hub, alice, mock_lz_relay):
    _request(hub, alice, RAIL_LZ, LZ_TWO, [], lz_cost(2))

    assert mock_lz_relay.call_count() == 1
    assert mock_lz_relay.last_value() == lz_cost(2)
    assert mock_lz_relay.last_block_number() == PINNED_BLOCK
    assert mock_lz_relay.last_lz_gas() == LZ_RECEIVE_GAS_LIMIT
    assert mock_lz_relay.last_read_gas() == LZ_READ_GAS_LIMIT
    assert mock_lz_relay.get_last_eids() == [BASE_EID, ARBITRUM_EID]


def test_lz_request_pays_no_surcharge(hub, alice, mock_lz_relay):
    """The LayerZero rail costs the protocol nothing, so exact fees are enough."""
    _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1))

    assert mock_lz_relay.last_value() == lz_cost(1)
    assert boa.env.get_balance(hub.address) == 0


def test_cre_request_pushes_fees_and_emits_trigger(hub, alice, mock_cre_relay):
    _request(hub, alice, RAIL_CRE, [], CCIP_TWO, cre_cost(2))
    event = _event(hub, "CREBlockhashRequested")

    # CCIP fees land in the relay, because onReport spends from its own balance
    assert boa.env.get_balance(mock_cre_relay.address) == ccip_max_fee(2)
    # the surcharge stays behind to fund CRE credits
    assert boa.env.get_balance(hub.address) == surcharge(2)

    assert event.requester == alice
    assert event.block_number == PINNED_BLOCK
    assert list(event.chain_selectors) == CCIP_TWO
    assert list(event.max_fees) == [ccip_max_fee(1), ccip_max_fee(1)]
    assert event.ccip_receive_gas_limit == CCIP_RECEIVE_GAS_LIMIT


def test_cre_request_computes_on_report_gas_from_target_count(hub, alice):
    """Write gas is derived on-chain, never taken from the caller."""
    _request(hub, alice, RAIL_CRE, [], CCIP_TWO, cre_cost(2))

    assert (
        _event(hub, "CREBlockhashRequested").on_report_gas_limit
        == BASE_ON_REPORT_GAS + 2 * CCIP_SEND_GAS
    )


def test_on_report_gas_follows_set_gas_params(hub, alice, dev_deployer):
    with boa.env.prank(dev_deployer):
        hub.set_gas_params(500_000, 111_000)

    _request(hub, alice, RAIL_CRE, [], CCIP_ONE, cre_cost(1))

    assert _event(hub, "CREBlockhashRequested").on_report_gas_limit == 500_000 + 111_000


def test_both_rails_from_one_call(hub, alice, mock_lz_relay, mock_cre_relay):
    _request(hub, alice, RAIL_BOTH, LZ_TWO, CCIP_TWO, lz_cost(2) + cre_cost(2))
    events = hub.get_logs()

    assert mock_lz_relay.call_count() == 1
    assert boa.env.get_balance(mock_cre_relay.address) == ccip_max_fee(2)

    lz_event = next(e for e in events if type(e).__name__ == "LZBlockhashRequested")
    cre_event = next(e for e in events if type(e).__name__ == "CREBlockhashRequested")
    # One request id ties the two legs together
    assert lz_event.request_id == cre_event.request_id
    assert lz_event.block_number == cre_event.block_number == PINNED_BLOCK


def test_rails_may_target_different_chains(hub, alice, mock_lz_relay):
    """Kava has no CCIP lane, so it rides the LayerZero list only."""
    _request(hub, alice, RAIL_BOTH, [KAVA_EID], CCIP_ONE, lz_cost(1) + cre_cost(1))

    assert mock_lz_relay.get_last_eids() == [KAVA_EID]
    assert list(_event(hub, "CREBlockhashRequested").chain_selectors) == CCIP_ONE


def test_request_ids_are_unique(hub, alice):
    first = _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1))
    second = _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1))

    assert first != second
    assert hub.nonce() == 2


def test_overpayment_is_returned(hub, alice):
    before = boa.env.get_balance(alice)
    _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1) + 10**17)

    assert boa.env.get_balance(alice) == before - lz_cost(1)


def test_lz_refund_is_swept_not_returned(hub, alice, mock_lz_relay, dev_deployer):
    """Endpoint dust comes back to the hub and joins the surcharge, by design."""
    with boa.env.prank(dev_deployer):
        mock_lz_relay.set_refund_bps(1_000)  # 10%

    _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1))

    assert boa.env.get_balance(hub.address) == lz_cost(1) // 10


def test_owner_can_withdraw_surcharge(hub, alice, dev_deployer):
    _request(hub, alice, RAIL_CRE, [], CCIP_ONE, cre_cost(1))
    accrued = boa.env.get_balance(hub.address)
    before = boa.env.get_balance(dev_deployer)

    with boa.env.prank(dev_deployer):
        hub.withdraw_eth(accrued)

    assert boa.env.get_balance(hub.address) == 0
    assert boa.env.get_balance(dev_deployer) == before + accrued
