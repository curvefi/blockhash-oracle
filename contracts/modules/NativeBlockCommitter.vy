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


# Same bound the header decoder uses
HEADER_SIZE: constant(uint256) = 1024
MAX_HEADERS: constant(uint256) = 128


@pure
@internal
def _walk(
    _block_number: uint256,
    _block_hash: bytes32,
    _headers: DynArray[Bytes[HEADER_SIZE], MAX_HEADERS],
) -> (uint256, bytes32):
    """
    @notice Follow block headers down from a known block
    @param _block_number Number of the known block
    @param _block_hash Its hash
    @param _headers RLP headers from that block downwards, one per step
    @return Number and hash of the parent of the last header, or the known block if there are none
    """
    block_number: uint256 = _block_number
    block_hash: bytes32 = _block_hash
    for header: Bytes[HEADER_SIZE] in _headers:
        assert keccak256(header) == block_hash, "Header does not match"
        # A header is an RLP list over 255 bytes: 0xf9, two length bytes, 0xa0, then the parent hash
        block_hash = extract32(header, 4)
        block_number -= 1
    return block_number, block_hash


@internal
def _commit(_block_oracle: IBlockOracle, _block_number: uint256, _block_hash: bytes32):
    """
    @notice Commit a block to the oracle unless it already holds that hash
    @dev A different hash already applied reverts in the oracle
    """
    if staticcall _block_oracle.get_block_hash(_block_number) != _block_hash:
        extcall _block_oracle.commit_block(_block_number, _block_hash)
