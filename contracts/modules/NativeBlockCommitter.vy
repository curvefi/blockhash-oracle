# pragma version 0.4.3
# pragma optimize gas

"""
@title Native Block Committer - what every native rail shares

@notice A chain that keeps its own record of Ethereum needs no bridge for block hashes. This
        module proves an older Ethereum block from one the chain already holds, by a chain of
        block headers each holding its parent's hash, and commits it to the BlockOracle.

@dev The contract importing this only says where its starting hash comes from. It must be the
     oracle's only committer: the oracle then trusts nothing but the chain itself.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

interface IBlockOracle:
    def commit_block(_block_number: uint256, _block_hash: bytes32) -> bool: nonpayable
    def get_block_hash(_block_number: uint256) -> bytes32: view
    def committer_votes(_committer: address, _block_number: uint256) -> bytes32: view


# Same bound the header decoder uses
HEADER_SIZE: constant(uint256) = 1024
MAX_HEADERS: constant(uint256) = 128


@pure
@internal
def _parent_hash(_header: Bytes[HEADER_SIZE], _block_hash: bytes32) -> bytes32:
    """
    @notice One step of a walk down the chain: check a header against its block's hash
    @dev Takes one header, not the list: an internal call copies its arguments, and a copy of
         the whole list costs over 100k gas in memory whatever its length
    @param _header RLP header of the block
    @param _block_hash The block's hash, already proven
    @return The parent's hash, proven by this header
    """
    assert keccak256(_header) == _block_hash, "Header does not match"
    # A header is an RLP list over 255 bytes: 0xf9, two length bytes, 0xa0, then the parent hash
    return extract32(_header, 4)


@internal
def _commit(_block_oracle: IBlockOracle, _block_number: uint256, _block_hash: bytes32):
    """
    @notice Vote for a block unless the oracle already holds that hash or this vote
    @dev A different hash already applied reverts in the oracle. Above threshold 1 a vote alone
         applies nothing, and repeating it would only log it again.
    """
    if staticcall _block_oracle.get_block_hash(_block_number) == _block_hash:
        return
    if staticcall _block_oracle.committer_votes(self, _block_number) == _block_hash:
        return
    extcall _block_oracle.commit_block(_block_number, _block_hash)
