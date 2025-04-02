"""Test for LZBlockRelay initialization."""

import pytest
from conftest import LZ_ENDPOINT


@pytest.mark.mainnet
def test_initialization(forked_env, lz_block_relay, dev_deployer):
    """Test initialization of the contract."""
    assert lz_block_relay.owner() == dev_deployer
    assert lz_block_relay.endpoint() == LZ_ENDPOINT
    assert lz_block_relay._storage.lz_receive_gas_limit.get() == 150_000

    # Read functionality should be disabled initially
    assert not lz_block_relay.read_enabled()
