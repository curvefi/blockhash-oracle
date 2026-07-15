"""Test for ChainlinkBlockRelay ccipReceive function (inbound CCIP message path)."""

import pytest
import boa
from conftest import CCIP_ROUTER


def _abi_encode_address(addr):
    """ABI-encode an address as Bytes[32] (left-padded with zeros)."""
    return boa.util.abi.abi_encode("address", addr)


def _build_ccip_message(source_selector, sender_address, block_number, block_hash, message_id=None):
    """Build an Any2EVMMessage tuple matching CCIP.vy's struct layout."""
    message_id = message_id or bytes(32)
    sender_bytes = _abi_encode_address(sender_address)
    data = boa.util.abi.abi_encode("(uint256,bytes32)", (block_number, block_hash))
    # (message_id, source_chain_selector, sender, data, token_amounts)
    return (message_id, source_selector, sender_bytes, data, [])


# ─── Access control ──────────────────────────────────────────────────────────


@pytest.mark.mainnet
def test_ccip_receive_only_router(forked_env, configured_relay, dev_deployer, block_data):
    """Test that ccipReceive rejects calls from any address other than the CCIP router."""
    source_selector = 111
    peer = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(source_selector, peer)

    message = _build_ccip_message(source_selector, peer, block_data["number"], block_data["hash"])
    stranger = boa.env.generate_address()

    with boa.env.prank(stranger):
        with boa.reverts("Only router"):
            configured_relay.ccipReceive(message)


@pytest.mark.mainnet
def test_ccip_receive_rejects_unregistered_sender(
    forked_env, configured_relay, dev_deployer, block_data
):
    """Test that ccipReceive rejects messages from a sender not registered as a peer."""
    source_selector = 111
    peer = boa.env.generate_address()
    impostor = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(source_selector, peer)

    message = _build_ccip_message(
        source_selector, impostor, block_data["number"], block_data["hash"]
    )

    with boa.env.prank(CCIP_ROUTER):
        with boa.reverts("Invalid sender"):
            configured_relay.ccipReceive(message)


@pytest.mark.mainnet
def test_ccip_receive_rejects_unregistered_chain(forked_env, configured_relay, block_data):
    """Rejects messages from a chain with no registered peer: unset selector reverts "No sender"."""
    unregistered_selector = 999
    any_sender = boa.env.generate_address()

    message = _build_ccip_message(
        unregistered_selector, any_sender, block_data["number"], block_data["hash"]
    )

    with boa.env.prank(CCIP_ROUTER):
        with boa.reverts("No sender"):
            configured_relay.ccipReceive(message)


# ─── Block commitment ─────────────────────────────────────────────────────────


@pytest.mark.mainnet
def test_ccip_receive_valid_message(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A valid CCIP message commits the block to the oracle but does NOT populate
    received_blocks — CCIP-sourced blocks are destination-only (not re-broadcast)."""
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]

    source_selector = 111
    peer = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(source_selector, peer)

    message = _build_ccip_message(source_selector, peer, test_block_number, test_block_hash)
    with boa.env.prank(CCIP_ROUTER):
        configured_relay.ccipReceive(message)

    # committed to the oracle
    assert (
        block_oracle.committer_votes(configured_relay.address, test_block_number) == test_block_hash
    )
    # but NOT recorded as a re-broadcastable CRE-sourced block
    assert configured_relay._storage.received_blocks.get() == {}


@pytest.mark.mainnet
def test_ccip_receive_multiple_blocks(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """Test committing multiple blocks via successive ccipReceive calls."""
    source_selector = 111
    peer = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(source_selector, peer)

    # One real block from block_data, plus a synthetic neighbour
    block_a_number = block_data["number"]
    block_a_hash = block_data["hash"]
    block_b_number = block_data["number"] + 1
    block_b_hash = bytes.fromhex("bbbb0000" * 8)

    with boa.env.prank(CCIP_ROUTER):
        configured_relay.ccipReceive(
            _build_ccip_message(source_selector, peer, block_a_number, block_a_hash)
        )
        configured_relay.ccipReceive(
            _build_ccip_message(source_selector, peer, block_b_number, block_b_hash)
        )

    assert block_oracle.committer_votes(configured_relay.address, block_a_number) == block_a_hash
    assert block_oracle.committer_votes(configured_relay.address, block_b_number) == block_b_hash


# ─── Idempotency / conflict (#4) ─────────────────────────────────────────────


@pytest.mark.mainnet
def test_ccip_receive_duplicate_same_hash_no_revert(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data
):
    """A duplicate CCIP delivery of an already-committed block is a no-op, not a revert."""
    n, h = block_data["number"], block_data["hash"]
    source_selector = 111
    peer = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(source_selector, peer)

    message = _build_ccip_message(source_selector, peer, n, h)
    with boa.env.prank(CCIP_ROUTER):
        configured_relay.ccipReceive(message)
        configured_relay.ccipReceive(message)  # duplicate: must not revert

    assert block_oracle.get_block_hash(n) == h


@pytest.mark.mainnet
def test_ccip_receive_conflicting_hash_reverts(
    forked_env, configured_relay, dev_deployer, block_data
):
    """A CCIP delivery of a different hash for an already-applied block reverts."""
    n, h = block_data["number"], block_data["hash"]
    conflicting = bytes.fromhex("ee" * 32)
    source_selector = 111
    peer = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        configured_relay.set_peer(source_selector, peer)

    with boa.env.prank(CCIP_ROUTER):
        configured_relay.ccipReceive(_build_ccip_message(source_selector, peer, n, h))
        with boa.reverts("Different blockhash already applied"):
            configured_relay.ccipReceive(_build_ccip_message(source_selector, peer, n, conflicting))
