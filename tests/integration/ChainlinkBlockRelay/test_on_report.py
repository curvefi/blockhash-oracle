"""Test for ChainlinkBlockRelay onReport function (CRE Forwarder delivery path)."""

import pytest
import boa
from conftest import (
    BASE_CHAIN_SELECTOR,
    ARBITRUM_CHAIN_SELECTOR,
    CCIP_RECEIVE_GAS_LIMIT,
    VALID_METADATA,
)

EMPTY_HASH = b"\x00" * 32


def _encode_report(
    block_number, block_hash, selectors=None, fees=None, gas_limit=CCIP_RECEIVE_GAS_LIMIT
):
    """ABI-encode the onReport payload matching ChainlinkBlockRelay's abi_decode call."""
    selectors = selectors or []
    fees = fees or []
    return boa.util.abi.abi_encode(
        "(uint256,bytes32,uint64[],uint256[],uint256)",
        (block_number, block_hash, selectors, fees, gas_limit),
    )


# ─── Access control ──────────────────────────────────────────────────────────


@pytest.mark.mainnet
def test_on_report_rejects_non_forwarder(forked_env, configured_relay, cre_forwarder, block_data):
    """Test that onReport rejects calls from addresses other than the forwarder."""
    report = _encode_report(block_data["number"], block_data["hash"])
    stranger = boa.env.generate_address()

    with boa.env.prank(stranger):
        with boa.reverts("Invalid sender"):
            configured_relay.onReport(VALID_METADATA, report)


@pytest.mark.mainnet
def test_on_report_reverts_without_workflow_identity(
    forked_env, chainlink_block_relay, block_oracle, dev_deployer, cre_forwarder, block_data
):
    """Strict enforcement: onReport reverts if the forwarder is enabled but no workflow
    identity (id/author/name) is configured."""
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_block_oracle(block_oracle.address)
        chainlink_block_relay.set_forwarder_address(cre_forwarder)
        block_oracle.add_committer(chainlink_block_relay.address, True)
        # deliberately NOT configuring expected_workflow_id / author / name

    report = _encode_report(block_data["number"], block_data["hash"])
    with boa.env.prank(cre_forwarder):
        with boa.reverts("Workflow parameters are not set"):
            chainlink_block_relay.onReport(VALID_METADATA, report)


@pytest.mark.mainnet
def test_on_report_successful_delivery(
    forked_env, configured_relay, block_oracle, cre_forwarder, block_data
):
    """A forwarder-delivered report with no broadcast targets: stores the block
    in received_blocks and commits it to the oracle (and does not revert)."""
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]
    report = _encode_report(test_block_number, test_block_hash)

    assert configured_relay._storage.received_blocks.get() == {}

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, report)

    # stored for later re-broadcast eligibility
    assert configured_relay._storage.received_blocks.get()[test_block_number] == test_block_hash
    # committed to the oracle
    assert (
        block_oracle.committer_votes(configured_relay.address, test_block_number) == test_block_hash
    )
    # no targets → no broadcast attempted
    events = configured_relay.get_logs()
    assert len([e for e in events if "BlockHashBroadcast" in str(e)]) == 0


# ─── Silent-return edge cases ────────────────────────────────────────────────


@pytest.mark.mainnet
def test_on_report_ignores_empty_block_hash(
    forked_env, configured_relay, cre_forwarder, block_data
):
    """Test that onReport silently returns when block_hash is empty(bytes32)."""
    report = _encode_report(block_data["number"], EMPTY_HASH)

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, report)  # must not revert

    assert configured_relay._storage.received_blocks.get() == {}


@pytest.mark.mainnet
def test_on_report_ignores_mismatched_selector_fee_arrays(
    forked_env, configured_relay, cre_forwarder, block_data
):
    """Test that onReport silently returns when selector and fee array lengths differ."""
    report = _encode_report(
        block_data["number"],
        block_data["hash"],
        selectors=[111, 222],
        fees=[10**14],  # length mismatch — any non-zero fee, no router call
    )

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, report)  # must not revert

    assert configured_relay._storage.received_blocks.get() == {}


# ─── Broadcast on delivery ───────────────────────────────────────────────────


@pytest.mark.mainnet
def test_on_report_triggers_broadcast(
    forked_env, configured_relay, block_oracle, cre_forwarder, dev_deployer, block_data
):
    """Test that onReport broadcasts to target chains when selectors are provided."""
    test_selectors = [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR]
    test_addresses = [boa.env.generate_address(), boa.env.generate_address()]

    with boa.env.prank(dev_deployer):
        configured_relay.set_peers(test_selectors, test_addresses)

    fees = configured_relay.quote_broadcast_fees(test_selectors, CCIP_RECEIVE_GAS_LIMIT)
    boa.env.set_balance(configured_relay.address, sum(fees))

    report = _encode_report(block_data["number"], block_data["hash"], test_selectors, fees)

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, report)

    events = configured_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    evt = broadcast_events[0]
    assert evt.block_number == block_data["number"]
    assert evt.block_hash == block_data["hash"]
    assert [t.chain_selector for t in evt.targets] == test_selectors
    assert [t.max_fee for t in evt.targets] == list(fees)


@pytest.mark.mainnet
def test_on_report_broadcast_only_sends_to_registered_peers(
    forked_env, configured_relay, cre_forwarder, dev_deployer, block_data
):
    """Test that broadcast skips unregistered chains and the event reflects only sent ones."""
    unregistered_selector = 999
    test_address = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(BASE_CHAIN_SELECTOR, test_address)

    fees = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)
    boa.env.set_balance(configured_relay.address, fees[0])

    # unregistered selector fee = 0, will be skipped by _broadcast_block
    report = _encode_report(
        block_data["number"],
        block_data["hash"],
        [BASE_CHAIN_SELECTOR, unregistered_selector],
        [fees[0], 0],
    )

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, report)

    events = configured_relay.get_logs()
    broadcast_events = [e for e in events if "BlockHashBroadcast" in str(e)]
    assert len(broadcast_events) == 1
    assert len(broadcast_events[0].targets) == 1
    assert broadcast_events[0].targets[0].chain_selector == BASE_CHAIN_SELECTOR


@pytest.mark.mainnet
def test_on_report_insufficient_balance_for_broadcast(
    forked_env, configured_relay, cre_forwarder, block_data
):
    """Test that onReport reverts when the contract lacks ETH to cover broadcast fees."""
    boa.env.set_balance(configured_relay.address, 0)

    # Any fee > 0 with balance = 0 triggers "Insufficient value" before ccipSend is reached
    report = _encode_report(block_data["number"], block_data["hash"], [111], [10**14])

    with boa.env.prank(cre_forwarder):
        with boa.reverts("Insufficient value"):
            configured_relay.onReport(VALID_METADATA, report)


# ─── Idempotency / conflict (#4) ─────────────────────────────────────────────


@pytest.mark.mainnet
def test_on_report_duplicate_reruns_fanout_without_reverting(
    forked_env, configured_relay, block_oracle, cre_forwarder, dev_deployer, block_data
):
    """A duplicate report for an already-committed block does not revert: the commit is
    skipped (idempotent) but the fanout still runs, so re-triggering retries delivery."""
    n, h = block_data["number"], block_data["hash"]

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, _encode_report(n, h))
    assert block_oracle.get_block_hash(n) == h

    peer = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(BASE_CHAIN_SELECTOR, peer)
    fees = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)
    boa.env.set_balance(configured_relay.address, fees[0])

    # same block again, now carrying a broadcast target
    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, _encode_report(n, h, [BASE_CHAIN_SELECTOR], fees))

    assert block_oracle.get_block_hash(n) == h  # commit was a no-op
    events = configured_relay.get_logs()
    assert len([e for e in events if "BlockHashBroadcast" in str(e)]) == 1  # fanout still fired


@pytest.mark.mainnet
def test_on_report_conflicting_hash_reverts(
    forked_env, configured_relay, cre_forwarder, block_data
):
    """A report for an already-applied block with a different hash reverts."""
    n, h = block_data["number"], block_data["hash"]
    conflicting = bytes.fromhex("bb" * 32)

    with boa.env.prank(cre_forwarder):
        configured_relay.onReport(VALID_METADATA, _encode_report(n, h))
        with boa.reverts("Different blockhash already applied"):
            configured_relay.onReport(VALID_METADATA, _encode_report(n, conflicting))
