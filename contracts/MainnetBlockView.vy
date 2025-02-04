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
def get_blockhash(_block_number: uint256 = block.number-65, _avoid_failure: Bool = True) ->  (bytes32, uint256):
    """
    @notice Get block hash for a given block number
    @param _block_number Block number to get hash for, defaults to block.number-65
    @return bytes32 Block hash
    """
    if _block_number >= block.number - 64 or _block_number <= block.number - 256:
        if _avoid_failure:
            # lzread is sensitive to reverts, so return (0,0) instead of reverting
            return (empty(bytes32), 0)
        else:
            revert("Block is too recent or too old")
    return (blockhash(_block_number), _block_number)
