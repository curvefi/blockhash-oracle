# pragma version 0.4.2
# pragma optimize gas

"""
@title Mainnet Block Viewer

@notice A contract that exposes recent blockhashes via view function.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

# https://eips.ethereum.org/EIPS/eip-2935
HISTORY_STORAGE_ADDRESS: constant(address) = 0x0000F90827F1C53a10cb7A02335B175320002935

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
    @param _avoid_failure If True, returns latest available block hash when requested block is unavailable
    @return Tuple of (actual block number, block hash)
    """
    # local copy of _block_number (to be able to overwrite)
    requested_block_number: uint256 = _block_number

    # another fallback to default argument
    # in case we want to avoid failure and don't know latest block (crosschain calls)
    if requested_block_number == 0:
        requested_block_number = block.number - 65

    if requested_block_number < block.number - 64:
        # We don't trust recent blocks because of possible reorgs
        if requested_block_number > block.number - 256:
            # This case can be handled by built-in
            return (requested_block_number, blockhash(requested_block_number))
        elif requested_block_number > block.number - 8192:
            # EIP-2935
            return (requested_block_number, self._history_storage_get(requested_block_number))

    # If we didn't return anything by now, we should fail (or fail gracefully)
    if _avoid_failure:
        # lzread is sensitive to reverts, so return (0,0) instead of reverting
        return (0, empty(bytes32))
    else:
        raise ("Block is too recent or too old")


@internal
@view
def _history_storage_get(_block_number: uint256) -> bytes32:
    return convert(
        raw_call(
            HISTORY_STORAGE_ADDRESS,
            abi_encode(_block_number),
            max_outsize=32,
            is_static_call=True,
        ), bytes32)
