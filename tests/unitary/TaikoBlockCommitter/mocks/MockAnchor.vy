# pragma version 0.4.3

"""
@title Mock Anchor

@notice Stand-in for Taiko's anchor contract: reports the latest Ethereum block a test set.
"""

struct BlockState:
    anchorBlockNumber: uint48
    ancestorsHash: bytes32


anchor_block_number: public(uint48)


@external
def set_anchor_block_number(_anchor_block_number: uint48):
    self.anchor_block_number = _anchor_block_number


@view
@external
def getBlockState() -> BlockState:
    return BlockState(anchorBlockNumber=self.anchor_block_number, ancestorsHash=empty(bytes32))
