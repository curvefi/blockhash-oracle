"""Test for ChainlinkBlockRelay on Ethereum with MainnetViewOracle as its oracle: a report is a
trigger, and only the chain's own hash is forwarded."""

import boa
import pytest

from conftest import (
    BASE_CHAIN_SELECTOR,
    CCIP_RECEIVE_GAS_LIMIT,
    CRE_FORWARDER,
    EMPTY_HASH,
    MAINNET_CHAIN_ID,
    NEWEST_BLOCK_AGE,
    VALID_METADATA,
    received,
)

pytestmark = pytest.mark.mainnet

WRONG_HASH = b"\xbd" * 32


def _encode_report(relay, block_number, block_hash, selectors=None, fees=None):
    return boa.util.abi.abi_encode(
        "(address,uint256,uint256,bytes32,uint64[],uint256[],uint256)",
        (
            relay.address,
            MAINNET_CHAIN_ID,
            block_number,
            block_hash,
            selectors or [],
            fees or [],
            CCIP_RECEIVE_GAS_LIMIT,
        ),
    )


def _add_base(relay, dev_deployer):
    """Register a peer on Base and fund the relay for one send to it; returns the fee"""
    with boa.env.prank(dev_deployer):
        relay.set_peers([BASE_CHAIN_SELECTOR], [boa.env.generate_address()])
    fees = relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)
    boa.env.set_balance(relay.address, sum(fees))
    return list(fees)


def test_report_with_the_chains_hash_is_broadcast(chainlink_relay, dev_deployer, block):
    number, block_hash = block
    fees = _add_base(chainlink_relay, dev_deployer)
    report = _encode_report(chainlink_relay, number, block_hash, [BASE_CHAIN_SELECTOR], fees)

    with boa.env.prank(CRE_FORWARDER):
        chainlink_relay.onReport(VALID_METADATA, report)

    broadcasts = [e for e in chainlink_relay.get_logs() if "BlockHashBroadcast" in str(e)]
    assert len(broadcasts) == 1
    assert (broadcasts[0].block_number, broadcasts[0].block_hash) == (number, block_hash)
    assert [t.chain_selector for t in broadcasts[0].targets] == [BASE_CHAIN_SELECTOR]
    assert received(chainlink_relay, number) == block_hash


def test_report_with_a_wrong_hash_reverts(chainlink_relay, dev_deployer, block):
    number, _ = block
    fees = _add_base(chainlink_relay, dev_deployer)
    report = _encode_report(chainlink_relay, number, WRONG_HASH, [BASE_CHAIN_SELECTOR], fees)

    with boa.env.prank(CRE_FORWARDER):
        with boa.reverts("Different blockhash already applied"):
            chainlink_relay.onReport(VALID_METADATA, report)

    assert received(chainlink_relay, number) == EMPTY_HASH
    assert boa.env.get_balance(chainlink_relay.address) == sum(fees)


def test_report_for_the_newest_block_the_view_serves_is_received(chainlink_relay, head, recent):
    number, block_hash = head - NEWEST_BLOCK_AGE, recent[NEWEST_BLOCK_AGE]

    with boa.env.prank(CRE_FORWARDER):
        chainlink_relay.onReport(
            VALID_METADATA, _encode_report(chainlink_relay, number, block_hash)
        )

    assert received(chainlink_relay, number) == block_hash


def test_report_with_a_wrong_hash_for_the_newest_block_reverts(chainlink_relay, head, recent):
    report = _encode_report(chainlink_relay, head - NEWEST_BLOCK_AGE, WRONG_HASH)

    with boa.env.prank(CRE_FORWARDER):
        with boa.reverts("Different blockhash already applied"):
            chainlink_relay.onReport(VALID_METADATA, report)


def test_report_with_the_chains_hash_one_block_too_recent_reverts(chainlink_relay, head, recent):
    number, block_hash = head - NEWEST_BLOCK_AGE + 1, recent[NEWEST_BLOCK_AGE - 1]

    with boa.env.prank(CRE_FORWARDER):
        with boa.reverts("Block outside view window"):
            chainlink_relay.onReport(
                VALID_METADATA, _encode_report(chainlink_relay, number, block_hash)
            )

    assert received(chainlink_relay, number) == EMPTY_HASH


@pytest.mark.parametrize("age", [NEWEST_BLOCK_AGE - 1, 9_000])
def test_report_for_a_block_outside_the_window_reverts(chainlink_relay, head, age):
    """Nothing to check the hash against, so the relay falls through to commit_block, which reverts."""
    report = _encode_report(chainlink_relay, head - age, WRONG_HASH)

    with boa.env.prank(CRE_FORWARDER):
        with boa.reverts("Block outside view window"):
            chainlink_relay.onReport(VALID_METADATA, report)

    assert received(chainlink_relay, head - age) == EMPTY_HASH


def test_reported_block_can_be_broadcast_again_by_anyone(chainlink_relay, dev_deployer, block):
    number, block_hash = block
    with boa.env.prank(CRE_FORWARDER):
        chainlink_relay.onReport(
            VALID_METADATA, _encode_report(chainlink_relay, number, block_hash)
        )
    fees = _add_base(chainlink_relay, dev_deployer)
    caller = boa.env.generate_address()
    boa.env.set_balance(caller, sum(fees))

    with boa.env.prank(caller):
        chainlink_relay.broadcast_block(
            number, [BASE_CHAIN_SELECTOR], fees, CCIP_RECEIVE_GAS_LIMIT, value=sum(fees)
        )

    broadcasts = [e for e in chainlink_relay.get_logs() if "BlockHashBroadcast" in str(e)]
    assert (broadcasts[0].block_number, broadcasts[0].block_hash) == (number, block_hash)


def test_block_the_relay_never_received_cannot_be_broadcast(chainlink_relay, dev_deployer, block):
    """The view knows the hash, but the relay still forwards only what a report brought it."""
    fees = _add_base(chainlink_relay, dev_deployer)
    caller = boa.env.generate_address()
    boa.env.set_balance(caller, sum(fees))

    with boa.env.prank(caller):
        with boa.reverts("Unknown source"):
            chainlink_relay.broadcast_block(
                block[0], [BASE_CHAIN_SELECTOR], fees, CCIP_RECEIVE_GAS_LIMIT, value=sum(fees)
            )
