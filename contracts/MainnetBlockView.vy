# pragma version 0.4.3
# pragma optimize gas

"""
@title Mainnet Block Viewer

@notice A contract that exposes recent blockhashes via a view function.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

from snekmate.utils import block_hash as snekmate_block_hash

@view
@external
def get_blockhash(
    _block_number: uint256 = block.number - 65, _avoid_failure: bool = False
) -> (uint256, bytes32):
    """
    @notice Get block hash for a given block number.
    @dev The valid range for historical block hashes is between the last 64
         and the last 8192 blocks.
    @param _block_number Block number to get hash for, defaults to block.number - 65.
    @param _avoid_failure If True, returns (0, 0x0) on failure instead of reverting.
    @return Tuple of (actual block number, block hash).
    """
    # Use a local variable for the requested block number.
    requested_block_number: uint256 = _block_number

    # If the default value was passed as 0 (e.g., from a cross-chain call
    # that doesn't know the current block number), set a safe default.
    if requested_block_number == 0:
        requested_block_number = block.number - 65

    # Check for invalid conditions first to exit early.
    # The requested block must be at least 64 blocks old for reorg protection
    # and not more than 8192 blocks old, which is the EVM's limit post EIP-2935.
    is_too_recent: bool = requested_block_number >= block.number - 64
    is_too_old: bool = requested_block_number <= block.number - 8192

    if is_too_recent or is_too_old:
        if _avoid_failure:
            # For sensitive callers (like LayerZero), return a zeroed response
            # instead of reverting the transaction.
            return 0, empty(bytes32)
        else:
            # Revert with a descriptive custom error.
            raise ("Block is too recent or too old")
    # If all checks pass, retrieve and return the blockhash.
    return requested_block_number, snekmate_block_hash._block_hash(requested_block_number)
