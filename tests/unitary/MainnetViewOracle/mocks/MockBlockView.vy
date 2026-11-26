# pragma version 0.4.3

"""
@title Mock Block View

@notice Stand-in for MainnetBlockView that answers every query with one preset (number, hash),
whatever was asked: the real view does that for block 0, which it reads as its default block.
"""

block_number: public(uint256)
block_hash: public(bytes32)


@external
def set_answer(_block_number: uint256, _block_hash: bytes32):
    self.block_number = _block_number
    self.block_hash = _block_hash


@view
@external
def get_blockhash(_block_number: uint256, _avoid_failure: bool) -> (uint256, bytes32):
    return self.block_number, self.block_hash
