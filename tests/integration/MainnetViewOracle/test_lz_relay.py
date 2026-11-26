"""Test for LZBlockRelay on Ethereum with MainnetViewOracle as its oracle. The endpoint is pranked:
whether LayerZero delivers a read of Ethereum to Ethereum is not something a fork can show."""

import boa
import pytest

from conftest import EMPTY_HASH, LZ_ENDPOINT, LZ_READ_CHANNEL, NEWEST_BLOCK_AGE, received

pytestmark = pytest.mark.mainnet

WRONG_HASH = b"\xbd" * 32
PEER_EID = 30110  # Arbitrum


def _deliver(relay, src_eid, block_number, block_hash):
    """lzReceive as the endpoint: a read response when src_eid is the read channel"""
    origin = (src_eid, boa.eval(f"convert({relay.address}, bytes32)"), 0)
    message = boa.util.abi.abi_encode("(uint256,bytes32)", (block_number, block_hash))
    with boa.env.prank(LZ_ENDPOINT):
        relay.lzReceive(origin, bytes(32), message, boa.env.generate_address(), b"")


def test_read_response_with_the_chains_hash_is_received(lz_relay, block):
    number, block_hash = block

    _deliver(lz_relay, LZ_READ_CHANNEL, number, block_hash)

    assert received(lz_relay, number) == block_hash


def test_read_response_for_the_newest_block_the_view_serves_is_received(lz_relay, head, recent):
    """The view's default block, which is what a read without a block number answers with."""
    number, block_hash = head - NEWEST_BLOCK_AGE, recent[NEWEST_BLOCK_AGE]

    _deliver(lz_relay, LZ_READ_CHANNEL, number, block_hash)

    assert received(lz_relay, number) == block_hash


def test_read_response_with_a_wrong_hash_reverts(lz_relay, block):
    with boa.reverts("Different blockhash already applied"):
        _deliver(lz_relay, LZ_READ_CHANNEL, block[0], WRONG_HASH)

    assert received(lz_relay, block[0]) == EMPTY_HASH


def test_read_response_for_a_block_outside_the_window_reverts(lz_relay, head):
    with boa.reverts("Block outside view window"):
        _deliver(lz_relay, LZ_READ_CHANNEL, head - 9_000, WRONG_HASH)


def test_peer_cannot_push_a_wrong_hash(lz_relay, dev_deployer, block):
    """Members are the relay's peers, so a compromised one can message it; the view still decides."""
    with boa.env.prank(dev_deployer):
        lz_relay.set_peers([PEER_EID], [lz_relay.address])

    with boa.reverts("Different blockhash already applied"):
        _deliver(lz_relay, PEER_EID, block[0], WRONG_HASH)


def test_peer_message_does_not_make_a_block_broadcastable(lz_relay, dev_deployer, block):
    number, block_hash = block
    with boa.env.prank(dev_deployer):
        lz_relay.set_peers([PEER_EID], [lz_relay.address])

    _deliver(lz_relay, PEER_EID, number, block_hash)

    assert received(lz_relay, number) == EMPTY_HASH
    with boa.reverts("Unknown source"):
        lz_relay.broadcast_block(number, [], [], 150_000)
