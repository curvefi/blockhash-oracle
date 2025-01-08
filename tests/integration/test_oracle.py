import boa
import pytest


def test_get_block_hash(forked_env, chain_name, oracle):
    """Test getting block hash from the oracle contract."""
    print(f"Running test on {chain_name} in fork mode!")
    block_number = boa.env.evm.patch.block_number
    print(f"Block number: {block_number}")
    block_hash = oracle.get_block_hash(block_number - 1)
    print(f"Block hash: {block_hash.hex()}")
