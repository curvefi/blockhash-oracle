# pragma version 0.4.3
# pragma optimize gas

"""
@title Taiko Block Committer

@notice Commits Ethereum block hashes to the BlockOracle from Taiko's own record of Ethereum.

@dev Taiko's anchor transaction saves a checkpoint (number, hash, state root) of an Ethereum
     block in the signal service, about one per 32 blocks. A commit starts from a checkpoint and
     may follow block headers down to any older block. Anyone may call: the caller picks the
     block, never the hash.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

from ..modules import NativeBlockCommitter as native


struct Checkpoint:
    blockNumber: uint48
    blockHash: bytes32
    stateRoot: bytes32


struct BlockState:
    anchorBlockNumber: uint48
    ancestorsHash: bytes32


interface ISignalService:
    def getCheckpoint(_blockNumber: uint48) -> Checkpoint: view


interface IAnchor:
    def getBlockState() -> BlockState: view


# Blocks a committed one must be behind Taiko's latest Ethereum block, itself a few behind
# Ethereum's head: the reorg margin MainnetBlockView gives the chains fed over bridges
MIN_DEPTH: public(constant(uint256)) = 64

BLOCK_ORACLE: public(immutable(native.IBlockOracle))
SIGNAL_SERVICE: public(immutable(ISignalService))
ANCHOR: public(immutable(IAnchor))


@deploy
def __init__(_block_oracle: address, _signal_service: address, _anchor: address):
    """
    @param _block_oracle BlockOracle on this chain, which must list this contract as a committer
    @param _signal_service Taiko's signal service, where the checkpoints are kept
    @param _anchor Taiko's anchor contract, which knows the latest Ethereum block Taiko holds
    """
    assert _block_oracle != empty(address), "Invalid block oracle"
    assert _signal_service != empty(address), "Invalid signal service"
    assert _anchor != empty(address), "Invalid anchor"
    BLOCK_ORACLE = native.IBlockOracle(_block_oracle)
    SIGNAL_SERVICE = ISignalService(_signal_service)
    ANCHOR = IAnchor(_anchor)


@external
def commit(
    _checkpoint_number: uint256,
    _headers: DynArray[Bytes[native.HEADER_SIZE], native.MAX_HEADERS] = [],
) -> (uint256, bytes32):
    """
    @notice Commit an Ethereum block Taiko holds a checkpoint for, or an ancestor of it
    @dev Reverts if Taiko holds no checkpoint for the block. Committing a block twice is a no-op.
    @param _checkpoint_number Ethereum block number of the checkpoint to start from
    @param _headers RLP headers from that block downwards, one per step. The block committed is
                    the parent of the last one; none commits the checkpoint's block
    @return Number and hash of the committed block
    """
    checkpoint: Checkpoint = staticcall SIGNAL_SERVICE.getCheckpoint(
        convert(_checkpoint_number, uint48)
    )
    assert convert(checkpoint.blockNumber, uint256) == _checkpoint_number, "Wrong checkpoint"
    assert checkpoint.blockHash != empty(bytes32), "Empty block hash"

    block_number: uint256 = 0
    block_hash: bytes32 = empty(bytes32)
    block_number, block_hash = native._walk(_checkpoint_number, checkpoint.blockHash, _headers)

    state: BlockState = staticcall ANCHOR.getBlockState()
    assert (
        block_number + MIN_DEPTH <= convert(state.anchorBlockNumber, uint256)
    ), "Block too recent"

    native._commit(BLOCK_ORACLE, block_number, block_hash)
    return block_number, block_hash
