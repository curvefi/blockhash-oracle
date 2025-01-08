import boa
import pytest


@pytest.mark.op_chains
def test_initialization(forked_env, chain_name, op_l1_storage):
    """Test fetching the last fetched block."""
    # print(f"Running test on {chain_name} in fork mode!")
    # last_fetched_block = op_l1_storage.last_fetched_block()
    # print(f"Last fetched block: {last_fetched_block}")
    assert op_l1_storage.last_fetched_block() > 1
