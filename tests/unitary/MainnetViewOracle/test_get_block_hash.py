"""Unit tests for MainnetViewOracle.get_block_hash against a view whose answer is preset."""

import boa
import pytest

EMPTY_HASH = b"\x00" * 32
BLOCK_NUMBER = 21579069
BLOCK_HASH = b"\xab" * 32


@pytest.fixture()
def block_view():
    return boa.load("tests/unitary/MainnetViewOracle/mocks/MockBlockView.vy")


@pytest.fixture()
def view_oracle(block_view):
    return boa.load("contracts/MainnetViewOracle.vy", block_view.address)


def test_hash_is_returned_for_the_block_the_view_answered(block_view, view_oracle):
    block_view.set_answer(BLOCK_NUMBER, BLOCK_HASH)

    assert view_oracle.get_block_hash(BLOCK_NUMBER) == BLOCK_HASH


@pytest.mark.parametrize("asked", [0, BLOCK_NUMBER - 1, BLOCK_NUMBER + 1])
def test_hash_of_another_block_is_not_handed_out(block_view, view_oracle, asked):
    """Asked for block 0 the view answers with its default block: that hash is not block 0's."""
    block_view.set_answer(BLOCK_NUMBER, BLOCK_HASH)

    assert view_oracle.get_block_hash(asked) == EMPTY_HASH


def test_out_of_range_answer_gives_no_hash(block_view, view_oracle):
    block_view.set_answer(0, EMPTY_HASH)

    assert view_oracle.get_block_hash(BLOCK_NUMBER) == EMPTY_HASH
    assert view_oracle.get_block_hash(0) == EMPTY_HASH
