"""Forked-mainnet tests for BlockhashRequestHub against the real relays.

The CRE half is a two-step simulation: the hub funds the relay and emits the trigger log, then the
test plays the part of the CRE workflow by delivering the report the workflow would have built from
that log. That exercises the whole permissionless path against the real CCIP router.
"""

import boa
import pytest
from boa.contracts.event_decoder import RawLogEntry

from conftest import (
    ARBITRUM_CHAIN_SELECTOR,
    ARBITRUM_EID,
    BASE_CHAIN_SELECTOR,
    BASE_EID,
    BASE_ON_REPORT_GAS,
    CCIP_RECEIVE_GAS_LIMIT,
    CCIP_SEND_GAS,
    CRE_FORWARDER,
    LZ_READ_GAS_LIMIT,
    LZ_RECEIVE_GAS_LIMIT,
    RAIL_BOTH,
    RAIL_CRE,
    RAIL_LZ,
    VALID_METADATA,
)

CCIP_TARGETS = [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR]
LZ_TARGETS = [BASE_EID, ARBITRUM_EID]


def _quote(hub, rails, eids, selectors):
    return hub.quote_request(
        rails, eids, selectors, CCIP_RECEIVE_GAS_LIMIT, LZ_RECEIVE_GAS_LIMIT, LZ_READ_GAS_LIMIT
    )


def _request(hub, user, rails, eids, selectors, block_number, value):
    with boa.env.prank(user):
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


def _requested_event(hub):
    return next(e for e in hub.get_logs() if type(e).__name__ == "CREBlockhashRequested")


def _deliver_report(relay, block_number, block_hash, event):
    """Play the CRE workflow: turn the trigger log into the report it would have written."""
    report = boa.util.abi.abi_encode(
        "(uint256,bytes32,uint64[],uint256[],uint256)",
        (
            block_number,
            block_hash,
            list(event.chain_selectors),
            list(event.max_fees),
            event.ccip_receive_gas_limit,
        ),
    )
    with boa.env.prank(CRE_FORWARDER):
        relay.onReport(VALID_METADATA, report)


def _sent_selectors(events):
    """destChainSelectors of the CCIPMessageSent events from the live CCIP onramp.

    The onramp is a forked mainnet contract unknown to boa, so its logs arrive raw and
    CCIPMessageSent indexes destChainSelector as topics[1]. The router's other logs (WETH
    Deposit/Transfer and friends) carry addresses there, which are far outside uint64, so
    narrowing to that range leaves exactly the chain selectors.
    """
    topics = [e.topics[1] for e in events if isinstance(e, RawLogEntry) and len(e.topics) >= 2]
    return [t for t in topics if t < 2**64]


@pytest.mark.mainnet
def test_cre_request_funds_the_relay_and_emits_the_trigger(hub, cre_relay, user, block_data):
    """The hub quotes the real router, pushes those fees to the relay and keeps the surcharge."""
    _, ccip_total, surcharge, total = _quote(hub, RAIL_CRE, [], CCIP_TARGETS)
    assert ccip_total > 0  # real router quote, not a stub

    _request(hub, user, RAIL_CRE, [], CCIP_TARGETS, block_data["number"], total)
    event = _requested_event(hub)

    assert boa.env.get_balance(cre_relay.address) == ccip_total
    assert boa.env.get_balance(hub.address) == surcharge
    assert list(event.chain_selectors) == CCIP_TARGETS
    assert event.block_number == block_data["number"]
    assert event.on_report_gas_limit == BASE_ON_REPORT_GAS + 2 * CCIP_SEND_GAS


@pytest.mark.mainnet
def test_cre_request_then_report_broadcasts_over_real_ccip(
    hub, cre_relay, oracle, user, block_data
):
    """End to end: request, then deliver the workflow's report and watch CCIP actually send."""
    _, _, _, total = _quote(hub, RAIL_CRE, [], CCIP_TARGETS)
    _request(hub, user, RAIL_CRE, [], CCIP_TARGETS, block_data["number"], total)
    event = _requested_event(hub)

    relay_balance_before = boa.env.get_balance(cre_relay.address)

    _deliver_report(cre_relay, block_data["number"], block_data["hash"], event)
    sent = _sent_selectors(cre_relay.get_logs())

    # every requested chain got a message, paid for out of what the hub pushed
    assert sorted(sent) == sorted(CCIP_TARGETS)  # exactly the requested chains, no extras
    assert boa.env.get_balance(cre_relay.address) < relay_balance_before
    # and the hash landed locally
    assert oracle.get_block_hash(block_data["number"]) == block_data["hash"]


@pytest.mark.mainnet
def test_unspent_headroom_stays_in_the_relay(hub, cre_relay, user, block_data):
    """max_fee is a cap: the router charges its live fee and the surplus becomes working capital."""
    _, ccip_total, _, total = _quote(hub, RAIL_CRE, [], CCIP_TARGETS)
    _request(hub, user, RAIL_CRE, [], CCIP_TARGETS, block_data["number"], total)
    event = _requested_event(hub)

    _deliver_report(cre_relay, block_data["number"], block_data["hash"], event)

    spent = ccip_total - boa.env.get_balance(cre_relay.address)
    assert 0 < spent < ccip_total  # headroom was quoted but not consumed


@pytest.mark.mainnet
def test_lz_request_reaches_the_endpoint(hub, lz_relay, user, block_data):
    """The LayerZero leg runs synchronously through the real endpoint."""
    lz_total, _, _, total = _quote(hub, RAIL_LZ, LZ_TARGETS, [])
    assert lz_total > 0  # real endpoint quote

    balance_before = boa.env.get_balance(user)
    _request(hub, user, RAIL_LZ, LZ_TARGETS, [], block_data["number"], total)

    # the fee left the user and no surcharge is taken on this rail
    assert boa.env.get_balance(user) == balance_before - lz_total
    events = hub.get_logs()
    assert any(type(e).__name__ == "LZBlockhashRequested" for e in events)


@pytest.mark.mainnet
def test_both_rails_from_one_call(hub, cre_relay, user, block_data):
    """One transaction drives both rails, each with its own target list."""
    lz_total, ccip_total, _, total = _quote(hub, RAIL_BOTH, LZ_TARGETS, CCIP_TARGETS)

    _request(hub, user, RAIL_BOTH, LZ_TARGETS, CCIP_TARGETS, block_data["number"], total)
    events = hub.get_logs()

    assert boa.env.get_balance(cre_relay.address) == ccip_total
    assert any(type(e).__name__ == "LZBlockhashRequested" for e in events)
    assert any(type(e).__name__ == "CREBlockhashRequested" for e in events)


@pytest.mark.mainnet
def test_overpayment_comes_back(hub, user, block_data):
    _, _, _, total = _quote(hub, RAIL_CRE, [], CCIP_TARGETS)

    balance_before = boa.env.get_balance(user)
    _request(hub, user, RAIL_CRE, [], CCIP_TARGETS, block_data["number"], total + 10**18)

    assert boa.env.get_balance(user) == balance_before - total


@pytest.mark.mainnet
def test_rejects_target_the_router_cannot_reach(hub, user, block_data):
    """An unconfigured peer quotes 0 on the real relay, which is the route check."""
    _, _, _, total = _quote(hub, RAIL_CRE, [], CCIP_TARGETS)
    unknown_selector = 5009297550715157269  # Ethereum mainnet, deliberately not a configured peer

    with boa.env.prank(user):
        with boa.reverts("No CCIP route"):
            hub.request(
                RAIL_CRE,
                [],
                [unknown_selector],
                block_data["number"],
                CCIP_RECEIVE_GAS_LIMIT,
                LZ_RECEIVE_GAS_LIMIT,
                LZ_READ_GAS_LIMIT,
                value=total,
            )
