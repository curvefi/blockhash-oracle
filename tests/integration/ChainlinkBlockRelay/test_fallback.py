"""Test for ChainlinkBlockRelay __default__ fallback function."""

import pytest
import boa


@pytest.mark.mainnet
def test_fallback_receives_eth(forked_env, chainlink_block_relay):
    """The contract accepts plain ETH transfers (e.g. CCIP fee refunds) and
    accumulates successive sends."""
    initial_balance = boa.env.get_balance(chainlink_block_relay.address)

    sender = boa.env.generate_address()
    boa.env.set_balance(sender, 10**18)

    # single transfer is received
    with boa.env.prank(sender):
        boa.env.raw_call(chainlink_block_relay.address, value=10**17)  # 0.1 ETH
    assert boa.env.get_balance(chainlink_block_relay.address) - initial_balance == 10**17

    # further transfers accumulate
    with boa.env.prank(sender):
        boa.env.raw_call(chainlink_block_relay.address, value=10**16)
        boa.env.raw_call(chainlink_block_relay.address, value=10**16)
    assert (
        boa.env.get_balance(chainlink_block_relay.address) - initial_balance == 10**17 + 2 * 10**16
    )
