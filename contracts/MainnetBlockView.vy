# pragma version ~=0.4


"""
@title Mainnet Block Viewer

@notice A contract that exposes recent blockhashes via view function.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

@deploy
def __init__():
    pass

@view
@external
def get_blockhash(_block_number: uint256 = block.number-65, _avoid_failure: bool = False) ->  (uint256, bytes32):
    """
    @notice Get block hash for a given block number
    @param _block_number Block number to get hash for, defaults to block.number-65
    @return bytes32 Block hash
    """

    # another fallback to default argument
    # in case we want to avoid failure and don't know latest block (crosschain calls)
    if _block_number == 0:
        _block_number = block.number-65

    # assert _block_number < block.number-64, "Block is too recent"
    # assert _block_number > block.number-256, "Block is too old"
    # we do not assert to avoid failure in lzread

    if _block_number > block.number - 256 and _block_number < block.number - 64:
        return (_block_number, blockhash(_block_number))
    else:
        if _avoid_failure:
            # lzread is sensitive to reverts, so return (0,0) instead of reverting
            return (0, empty(bytes32))
        else:
            raise("Block is too recent or too old")
