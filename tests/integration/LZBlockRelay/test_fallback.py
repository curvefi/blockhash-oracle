"""Test for LZBlockRelay __default__ fallback function."""

import pytest
import boa


@pytest.mark.mainnet
def test_fallback(forked_env, lz_block_relay):
    """Test the default fallback function to receive ETH."""
    # Check initial balance
    initial_balance = boa.env.get_balance(lz_block_relay.address)

    # Send ETH directly to contract
    sender = boa.env.generate_address()
    boa.env.set_balance(sender, 10**18)  # 1 ETH

    with boa.env.prank(sender):
        boa.env.raw_call(
            lz_block_relay.address,
            value=10**17,  # 0.1 ETH
        )

    # Check balance increased
    final_balance = boa.env.get_balance(lz_block_relay.address)
    assert final_balance - initial_balance == 10**17
