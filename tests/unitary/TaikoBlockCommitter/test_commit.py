"""Unit tests for TaikoBlockCommitter.commit against a mock signal service and anchor."""

import boa
import pytest
from eth_utils import keccak

EMPTY_ADDRESS = boa.eval("empty(address)")
EMPTY_HASH = b"\x00" * 32
BLOCK_HASH = b"\xab" * 32
OTHER_HASH = b"\xbd" * 32

MIN_DEPTH = 64
MAX_HEADERS = 128
# The latest Ethereum block the mock anchor reports
ANCHOR_BLOCK = 21_579_069
# A block deep enough to be committed straight from its checkpoint
OLD_BLOCK = ANCHOR_BLOCK - MIN_DEPTH


def header_chain(count, seed=b"block"):
    """Stand-ins for `count` linked block headers, newest first: each holds its parent's hash where
    a real header does. Returns (headers, hash of the newest block, hash of the block they prove)."""
    proven = keccak(seed)
    block_hash, headers = proven, []
    for i in range(count):
        header = b"\xf9\x02\x18\xa0" + block_hash + bytes([i % 256]) * 500
        headers.append(header)
        block_hash = keccak(header)
    return headers[::-1], block_hash, proven


@pytest.fixture(autouse=True)
def taikos_latest_block(anchor):
    anchor.set_anchor_block_number(ANCHOR_BLOCK)


def _commits(committer):
    return [e for e in committer.get_logs() if "CommitBlock" in str(e)]


def test_checkpoint_block_is_committed_by_anyone(committer, block_oracle, signal_service):
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, BLOCK_HASH)

    with boa.env.prank(boa.env.generate_address()):
        assert committer.commit(OLD_BLOCK) == (OLD_BLOCK, BLOCK_HASH)

    assert block_oracle.get_block_hash(OLD_BLOCK) == BLOCK_HASH
    assert block_oracle.last_confirmed_block_number() == OLD_BLOCK


@pytest.mark.parametrize("count", [1, MIN_DEPTH, MAX_HEADERS])
def test_ancestor_is_committed_through_headers(committer, block_oracle, signal_service, count):
    headers, newest_hash, proven_hash = header_chain(count)
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, newest_hash)

    assert committer.commit(OLD_BLOCK, headers) == (OLD_BLOCK - count, proven_hash)

    assert block_oracle.get_block_hash(OLD_BLOCK - count) == proven_hash
    assert block_oracle.get_block_hash(OLD_BLOCK) == EMPTY_HASH


def test_newest_checkpoint_reaches_a_deep_enough_block_through_headers(
    committer, block_oracle, signal_service
):
    headers, newest_hash, proven_hash = header_chain(MIN_DEPTH)
    signal_service.set_checkpoint(ANCHOR_BLOCK, ANCHOR_BLOCK, newest_hash)

    committer.commit(ANCHOR_BLOCK, headers)

    assert block_oracle.get_block_hash(ANCHOR_BLOCK - MIN_DEPTH) == proven_hash


@pytest.mark.parametrize("count", [0, 1, MIN_DEPTH - 1])
def test_block_too_close_to_taikos_latest_reverts(committer, block_oracle, signal_service, count):
    headers, newest_hash, _ = header_chain(count)
    signal_service.set_checkpoint(ANCHOR_BLOCK, ANCHOR_BLOCK, newest_hash)

    with boa.reverts("Block too recent"):
        committer.commit(ANCHOR_BLOCK, headers)

    assert block_oracle.last_confirmed_block_number() == 0


def test_depth_is_counted_from_the_anchor_not_from_the_checkpoint(
    committer, signal_service, anchor
):
    signal_service.set_checkpoint(OLD_BLOCK + 1, OLD_BLOCK + 1, BLOCK_HASH)
    with boa.reverts("Block too recent"):
        committer.commit(OLD_BLOCK + 1)

    anchor.set_anchor_block_number(ANCHOR_BLOCK + 1)

    committer.commit(OLD_BLOCK + 1)


def test_header_that_was_changed_reverts(committer, signal_service):
    headers, newest_hash, _ = header_chain(5)
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, newest_hash)
    headers[2] = headers[2][:-1] + b"\x00"

    with boa.reverts("Header does not match"):
        committer.commit(OLD_BLOCK, headers)


def test_header_with_another_parent_hash_reverts_at_the_next_step(committer, signal_service):
    """Swapping the parent hash changes the header's own hash, so it is caught where it stands."""
    headers, newest_hash, _ = header_chain(5)
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, newest_hash)
    headers[4] = headers[4][:4] + OTHER_HASH + headers[4][36:]

    with boa.reverts("Header does not match"):
        committer.commit(OLD_BLOCK, headers)


@pytest.mark.parametrize("order", ["reversed", "gap", "from_the_parent"])
def test_headers_that_do_not_link_revert(committer, signal_service, order):
    headers, newest_hash, _ = header_chain(5)
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, newest_hash)
    broken = {
        "reversed": headers[::-1],
        "gap": headers[:2] + headers[3:],
        "from_the_parent": headers[1:],
    }[order]

    with boa.reverts("Header does not match"):
        committer.commit(OLD_BLOCK, broken)


def test_header_too_short_to_hold_a_parent_hash_reverts(committer, signal_service):
    header = b"\xf9\x02\x18\xa0" + b"\x01" * 31
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, keccak(header))

    with boa.reverts():
        committer.commit(OLD_BLOCK, [header])


def test_block_taiko_holds_no_checkpoint_for_reverts(committer):
    with boa.reverts("SS_CHECKPOINT_NOT_FOUND"):
        committer.commit(OLD_BLOCK)


def test_checkpoint_of_another_block_reverts(committer, signal_service):
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK - 1, BLOCK_HASH)

    with boa.reverts("Wrong checkpoint"):
        committer.commit(OLD_BLOCK)


def test_checkpoint_without_a_hash_reverts(committer, signal_service):
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, EMPTY_HASH)

    with boa.reverts("Empty block hash"):
        committer.commit(OLD_BLOCK)


def test_committing_a_block_twice_is_a_noop(committer, block_oracle, signal_service):
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, BLOCK_HASH)
    committer.commit(OLD_BLOCK)
    assert len(_commits(committer)) == 1

    assert committer.commit(OLD_BLOCK) == (OLD_BLOCK, BLOCK_HASH)

    assert _commits(committer) == []
    assert block_oracle.get_block_hash(OLD_BLOCK) == BLOCK_HASH


def test_block_the_oracle_holds_another_hash_for_reverts(
    committer, block_oracle, signal_service, dev_deployer
):
    other_committer = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(other_committer)
    with boa.env.prank(other_committer):
        block_oracle.commit_block(OLD_BLOCK, OTHER_HASH)
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, BLOCK_HASH)

    with boa.reverts("Already applied"):
        committer.commit(OLD_BLOCK)


def test_commit_reverts_until_the_oracle_lists_the_committer(
    committer, block_oracle, signal_service, dev_deployer
):
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(committer.address)
    signal_service.set_checkpoint(OLD_BLOCK, OLD_BLOCK, BLOCK_HASH)

    with boa.reverts("Not authorized"):
        committer.commit(OLD_BLOCK)


def test_addresses_and_depth_are_readable(committer, block_oracle, signal_service, anchor):
    assert committer.BLOCK_ORACLE() == block_oracle.address
    assert committer.SIGNAL_SERVICE() == signal_service.address
    assert committer.ANCHOR() == anchor.address
    assert committer.MIN_DEPTH() == MIN_DEPTH


@pytest.mark.parametrize(
    "missing", ["Invalid block oracle", "Invalid signal service", "Invalid anchor"]
)
def test_every_address_is_required(block_oracle, signal_service, anchor, missing):
    addresses = {
        "Invalid block oracle": block_oracle.address,
        "Invalid signal service": signal_service.address,
        "Invalid anchor": anchor.address,
    }
    addresses[missing] = EMPTY_ADDRESS

    with boa.reverts(missing):
        boa.load("contracts/native/TaikoBlockCommitter.vy", *addresses.values())
