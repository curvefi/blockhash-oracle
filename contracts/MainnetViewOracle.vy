# pragma version 0.4.3
# pragma optimize gas

"""
@title Mainnet View Oracle

@notice Fills the oracle slot of a block relay deployed on Ethereum, answering from
        MainnetBlockView instead of from committer votes.

@dev A relay asks its oracle for a block's hash before it commits or broadcasts one, and
     reverts when the hash it was handed differs. Here the oracle's answer is the chain's
     own hash, so a relay on Ethereum only forwards hashes Ethereum confirms and whatever
     triggered it (a CRE report, a LayerZero read) is a trigger, not a source.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

interface IMainnetBlockView:
    def get_blockhash(_block_number: uint256, _avoid_failure: bool) -> (uint256, bytes32): view


# Newest block MainnetBlockView serves, counted back from the head
NEWEST_BLOCK_AGE: constant(uint256) = 65

BLOCK_VIEW: public(immutable(IMainnetBlockView))


@deploy
def __init__(_block_view: address):
    """
    @param _block_view MainnetBlockView on this chain
    """
    assert _block_view != empty(address), "Invalid block view"
    BLOCK_VIEW = IMainnetBlockView(_block_view)


@view
@external
def get_block_hash(_block_number: uint256) -> bytes32:
    """
    @notice Hash of a block inside MainnetBlockView's window, empty outside it
    @param _block_number Block number to get the hash for
    """
    block_number: uint256 = 0
    block_hash: bytes32 = empty(bytes32)
    block_number, block_hash = staticcall BLOCK_VIEW.get_blockhash(_block_number, True)
    # The view answers 0 with its default block, and anything out of range with (0, empty)
    if block_number != _block_number:
        return empty(bytes32)
    return block_hash


@view
@external
def last_confirmed_block_number() -> uint256:
    """
    @notice Newest block this oracle has a hash for
    """
    return block.number - NEWEST_BLOCK_AGE


@view
@external
def committer_votes(_committer: address, _block_number: uint256) -> bytes32:
    """
    @notice Always empty: nobody votes here
    """
    return empty(bytes32)


@external
def commit_block(_block_number: uint256, _block_hash: bytes32) -> bool:
    """
    @notice Always reverts. A relay only gets here with a block outside the view's window,
            whose hash cannot be checked
    """
    raise "Block outside view window"
