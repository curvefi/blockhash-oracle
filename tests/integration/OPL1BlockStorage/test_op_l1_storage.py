import pytest


@pytest.mark.op_chains
def test_fetching_blocks(forked_env, op_l1_storage):
    print(op_l1_storage.last_fetched_block())
