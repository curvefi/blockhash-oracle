"""Test for MainnetViewOracle: the oracle interface a relay uses, answered from MainnetBlockView."""

import boa
import pytest

from conftest import (
    EMPTY_ADDRESS,
    EMPTY_HASH,
    NEWEST_BLOCK_AGE,
    OLDEST_BLOCK_AGE,
    RECENT_BLOCK_AGE,
)

pytestmark = pytest.mark.mainnet


def test_hash_is_the_chains_own(view_oracle, block):
    number, block_hash = block
    assert view_oracle.get_block_hash(number) == block_hash


def test_hash_agrees_with_the_view_across_its_window(view_oracle, mainnet_block_view, head):
    for age in (OLDEST_BLOCK_AGE, 4_000, 257):
        assert (
            view_oracle.get_block_hash(head - age)
            == mainnet_block_view.get_blockhash(head - age)[1]
        )
        assert view_oracle.get_block_hash(head - age) != EMPTY_HASH


@pytest.mark.parametrize("age", [NEWEST_BLOCK_AGE - 1, 0, -1, OLDEST_BLOCK_AGE + 1])
def test_hash_is_empty_outside_the_window(view_oracle, head, age):
    assert view_oracle.get_block_hash(head - age) == EMPTY_HASH


@pytest.mark.parametrize("age", [NEWEST_BLOCK_AGE, RECENT_BLOCK_AGE])
def test_hash_is_the_chains_own_for_a_recent_block(view_oracle, head, recent, age):
    assert view_oracle.get_block_hash(head - age) == recent[age]


def test_hash_is_empty_one_block_inside_the_reorg_margin(view_oracle, head, recent):
    assert view_oracle.get_block_hash(head - NEWEST_BLOCK_AGE + 1) == EMPTY_HASH


def test_block_zero_has_no_hash(view_oracle, mainnet_block_view, recent):
    """The view reads 0 as its default block; the oracle must not hand that hash out for block 0."""
    assert mainnet_block_view.get_blockhash(0, True)[1] == recent[NEWEST_BLOCK_AGE]
    assert view_oracle.get_block_hash(0) == EMPTY_HASH


def test_last_confirmed_is_the_newest_block_the_view_serves(view_oracle, mainnet_block_view, head):
    assert view_oracle.last_confirmed_block_number() == head - NEWEST_BLOCK_AGE
    assert mainnet_block_view.get_blockhash()[0] == head - NEWEST_BLOCK_AGE


def test_nobody_votes(view_oracle, block):
    assert view_oracle.committer_votes(boa.env.generate_address(), block[0]) == EMPTY_HASH


def test_commit_always_reverts(view_oracle, block):
    number, block_hash = block
    with boa.reverts("Block outside view window"):
        view_oracle.commit_block(number, block_hash)


def test_block_view_is_required(forked_env):
    with boa.reverts("Invalid block view"):
        boa.load("contracts/MainnetViewOracle.vy", EMPTY_ADDRESS)
