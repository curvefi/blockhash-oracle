# pragma version 0.4.1
# pragma optimize gas

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
def get_blockhash(
    _block_number: uint256 = block.number - 65, _avoid_failure: bool = False
) -> (uint256, bytes32):
    """
    @notice Get block hash for a given block number
    @param _block_number Block number to get hash for, defaults to block.number-65
    @return bytes32 Block hash
    """
    # local copy of _block_number (to be able to overwrite)
    requested_block_number: uint256 = _block_number

    # another fallback to default argument
    # in case we want to avoid failure and don't know latest block (crosschain calls)
    if requested_block_number == 0:
        requested_block_number = block.number - 65

    if requested_block_number >= block.number - 256 and requested_block_number < block.number - 64:
        return (requested_block_number, blockhash(requested_block_number))
    else:
        if _avoid_failure:
            # lzread is sensitive to reverts, so return (0,0) instead of reverting
            return (0, empty(bytes32))
        else:
            raise ("Block is too recent or too old")
