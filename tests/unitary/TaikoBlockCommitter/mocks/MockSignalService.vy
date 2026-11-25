# pragma version 0.4.3

"""
@title Mock Signal Service

@notice Stand-in for Taiko's signal service: answers with the checkpoints a test saved and
reverts for every other block, as the real one does.
"""

struct Checkpoint:
    blockNumber: uint48
    blockHash: bytes32
    stateRoot: bytes32


checkpoints: HashMap[uint48, Checkpoint]
saved: HashMap[uint48, bool]


@external
def set_checkpoint(_asked: uint48, _block_number: uint48, _block_hash: bytes32):
    """
    @notice Answer queries for `_asked` with a checkpoint of `_block_number`
    """
    self.checkpoints[_asked] = Checkpoint(
        blockNumber=_block_number, blockHash=_block_hash, stateRoot=empty(bytes32)
    )
    self.saved[_asked] = True


@view
@external
def getCheckpoint(_blockNumber: uint48) -> Checkpoint:
    assert self.saved[_blockNumber], "SS_CHECKPOINT_NOT_FOUND"
    return self.checkpoints[_blockNumber]
