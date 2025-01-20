# pragma version ~=0.4


"""
@title Mainnet Block Viewer

@notice A contract that exposes recent blockhashes via view function.

@license Copyright (c) Curve.Fi, 2020-2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

@deploy
def __init__():
    pass

@view
@external
def get_blockhash(_block_number: uint256 = block.number-65) ->  (bytes32, uint256):
    """
    @notice Get block hash for a given block number
    @param _block_number Block number to get hash for, defaults to block.number-65
    @return bytes32 Block hash
    """
    assert _block_number <= block.number-65, "Block is too recent"
    assert _block_number > block.number-256, "Block is too old"

    # return BlockData(block_hash=blockhash(_block_number), block_number=_block_number)
    return (blockhash(_block_number), _block_number)
