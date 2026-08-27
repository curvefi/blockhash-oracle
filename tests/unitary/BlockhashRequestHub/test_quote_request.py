from conftest import (
    CCIP_ONE,
    CCIP_RECEIVE_GAS_LIMIT,
    CCIP_TWO,
    LZ_READ_GAS_LIMIT,
    LZ_RECEIVE_GAS_LIMIT,
    LZ_TWO,
    RAIL_BOTH,
    RAIL_CRE,
    RAIL_LZ,
    ccip_max_fee,
    lz_cost,
    surcharge,
)


def _quote(hub, rails, eids, selectors):
    return hub.quote_request(
        rails, eids, selectors, CCIP_RECEIVE_GAS_LIMIT, LZ_RECEIVE_GAS_LIMIT, LZ_READ_GAS_LIMIT
    )


def test_quote_lz_only(hub):
    lz_total, ccip_total, fee, total = _quote(hub, RAIL_LZ, LZ_TWO, [])

    assert lz_total == lz_cost(2)
    assert ccip_total == 0
    assert fee == 0  # no surcharge on the LayerZero rail, it costs the protocol nothing
    assert total == lz_total


def test_quote_cre_only(hub):
    lz_total, ccip_total, fee, total = _quote(hub, RAIL_CRE, [], CCIP_TWO)

    assert lz_total == 0
    assert ccip_total == ccip_max_fee(2)
    assert fee == surcharge(2)
    assert total == ccip_total + fee


def test_quote_both_rails_sums_the_legs(hub):
    lz_total, ccip_total, fee, total = _quote(hub, RAIL_BOTH, LZ_TWO, CCIP_TWO)

    assert lz_total == lz_cost(2)
    assert ccip_total == ccip_max_fee(2)
    assert fee == surcharge(2)
    assert total == lz_total + ccip_total + fee


def test_quote_scales_with_target_count(hub):
    one = _quote(hub, RAIL_CRE, [], CCIP_ONE)
    two = _quote(hub, RAIL_CRE, [], CCIP_TWO)

    assert two[1] == 2 * one[1]
    assert two[2] > one[2]


def test_rails_take_independent_target_lists(hub):
    """A chain reachable on only one rail simply appears in only one list."""
    lz_total, ccip_total, _, _ = _quote(hub, RAIL_BOTH, LZ_TWO, CCIP_ONE)

    assert lz_total == lz_cost(2)
    assert ccip_total == ccip_max_fee(1)


def test_ccip_quote_carries_the_multiplier(hub):
    """max_fee is a cap, not a payment, so headroom shows up here and costs nothing unless used."""
    _, ccip_total, _, _ = _quote(hub, RAIL_CRE, [], CCIP_ONE)

    assert ccip_total == ccip_max_fee(1)
    assert ccip_total > 0
