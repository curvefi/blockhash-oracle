"""Test for TaikoBlockCommitter on a fork of Taiko: the checkpoints are Taiko's own, and every
committed hash is compared with Ethereum's."""

import boa
import pytest
from eth_utils import keccak

from conftest import ANCHOR, EMPTY_HASH, MIN_DEPTH, SIGNAL_SERVICE, encode_header

pytestmark = pytest.mark.taiko

FAKE_HASH = b"\xfa" * 32


def _save_checkpoint(sender, block_number):
    """Try to write a checkpoint as `sender`; True if the signal service took it"""
    data = keccak(text="saveCheckpoint((uint48,bytes32,bytes32))")[:4]
    data += block_number.to_bytes(32, "big") + FAKE_HASH + FAKE_HASH
    boa.env.set_balance(sender, 10**18)
    try:
        return not boa.env.raw_call(to_address=SIGNAL_SERVICE, sender=sender, data=data).is_error
    except Exception:
        return False


def test_taikos_latest_block_has_a_checkpoint_with_ethereums_hash(
    signal_service, anchor_block, ethereum
):
    number, block_hash, state_root = signal_service.getCheckpoint(anchor_block)
    block = ethereum.eth.get_block(anchor_block)

    assert number == anchor_block
    assert (block_hash, state_root) == (bytes(block["hash"]), bytes(block["stateRoot"]))


def test_checkpoints_are_kept(checkpoints):
    assert len(checkpoints) >= 3


def test_old_checkpoint_is_committed_as_it_is(committer, block_oracle, old_checkpoint, ethereum):
    block_hash = bytes(ethereum.eth.get_block(old_checkpoint)["hash"])

    with boa.env.prank(boa.env.generate_address()):
        assert committer.commit(old_checkpoint) == (old_checkpoint, block_hash)

    assert block_oracle.get_block_hash(old_checkpoint) == block_hash


def test_newest_checkpoint_is_too_recent_as_it_is(committer, block_oracle, anchor_block):
    with boa.reverts("Block too recent"):
        committer.commit(anchor_block)

    assert block_oracle.get_block_hash(anchor_block) == EMPTY_HASH


@pytest.mark.parametrize("depth", [MIN_DEPTH, MIN_DEPTH + 20])
def test_block_between_checkpoints_is_committed_through_headers(
    committer, block_oracle, anchor_block, ethereum, ethereum_headers, depth
):
    target = anchor_block - depth
    block_hash = bytes(ethereum.eth.get_block(target)["hash"])

    assert committer.commit(anchor_block, ethereum_headers(anchor_block, depth)) == (
        target,
        block_hash,
    )

    assert block_oracle.get_block_hash(target) == block_hash
    assert block_oracle.last_confirmed_block_number() == target


def test_committed_block_gives_consumers_its_state_root(
    committer, block_oracle, block_headers_decoder, anchor_block, ethereum, ethereum_headers
):
    target = anchor_block - MIN_DEPTH
    block = ethereum.eth.get_block(target)
    committer.commit(anchor_block, ethereum_headers(anchor_block, MIN_DEPTH))

    block_headers_decoder.submit_block_header(block_oracle.address, encode_header(block))

    assert block_oracle.get_state_root(target) == bytes(block["stateRoot"])


def test_one_header_short_of_the_depth_reverts(committer, anchor_block, ethereum_headers):
    with boa.reverts("Block too recent"):
        committer.commit(anchor_block, ethereum_headers(anchor_block, MIN_DEPTH - 1))


def test_header_that_was_changed_reverts(committer, block_oracle, anchor_block, ethereum_headers):
    headers = ethereum_headers(anchor_block, MIN_DEPTH)
    headers[10] = headers[10][:50] + bytes([headers[10][50] ^ 1]) + headers[10][51:]

    with boa.reverts("Header does not match"):
        committer.commit(anchor_block, headers)

    assert block_oracle.last_confirmed_block_number() == 0


def test_block_taiko_holds_no_checkpoint_for_reverts(committer, old_checkpoint):
    with boa.reverts():
        committer.commit(old_checkpoint - 1)


def test_only_taikos_anchor_writes_checkpoints(signal_service, anchor_block):
    """The committer is as trustworthy as whoever writes the checkpoints: Taiko's own anchor
    transaction, nobody else."""
    new_block = anchor_block + 1

    assert not _save_checkpoint(boa.env.generate_address(), new_block)
    assert _save_checkpoint(ANCHOR, new_block)
    assert signal_service.getCheckpoint(new_block)[1] == FAKE_HASH
