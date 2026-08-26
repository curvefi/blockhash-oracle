import boa

from conftest import (
    CCIP_ONE,
    CCIP_RECEIVE_GAS_LIMIT,
    CCIP_TWO,
    CRE_DEDUP_WINDOW,
    LZ_READ_GAS_LIMIT,
    LZ_RECEIVE_GAS_LIMIT,
    PINNED_BLOCK,
    RAIL_CRE,
    cre_cost,
)


def _request(hub, caller, selectors=CCIP_ONE, block_number=PINNED_BLOCK):
    with boa.env.prank(caller):
        return hub.request(
            RAIL_CRE,
            [],
            selectors,
            block_number,
            CCIP_RECEIVE_GAS_LIMIT,
            LZ_RECEIVE_GAS_LIMIT,
            LZ_READ_GAS_LIMIT,
            value=cre_cost(len(selectors)),
        )


# ─── duplicate suppression ───────────────────────────────────


def test_identical_request_is_rejected(hub, alice):
    _request(hub, alice)

    with boa.reverts("Duplicate request pending"):
        _request(hub, alice)


def test_different_targets_are_not_a_duplicate(hub, alice):
    _request(hub, alice, selectors=CCIP_ONE)
    _request(hub, alice, selectors=CCIP_TWO)


def test_different_block_is_not_a_duplicate(hub, alice):
    _request(hub, alice)
    _request(hub, alice, block_number=PINNED_BLOCK + 1)


def test_duplicate_allowed_once_the_window_expires(hub, alice):
    _request(hub, alice)
    # the dedup window is well inside the liveness timeout, so only dedup is under test here
    boa.env.time_travel(seconds=CRE_DEDUP_WINDOW + 1)

    _request(hub, alice)


def test_zero_window_disables_dedup(hub, alice, dev_deployer):
    with boa.env.prank(dev_deployer):
        hub.set_cre_dedup_window(0)

    _request(hub, alice)
    _request(hub, alice)
