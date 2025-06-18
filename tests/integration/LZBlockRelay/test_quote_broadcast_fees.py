"""Test for LZBlockRelay quote_broadcast_fees function."""

import pytest
import boa


@pytest.mark.mainnet
def test_quote_broadcast_fees(forked_env, lz_block_relay, dev_deployer):
    """Test quoting fees for broadcasting to multiple chains."""
    # Setup peers for testing
    test_eids = [30110, 30111, 30112]  # Target chain IDs (arb, opt, ...)

    test_addresses = [
        boa.env.generate_address(),
        boa.env.generate_address(),
        boa.env.generate_address(),
    ]

    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers(test_eids, test_addresses)

    # Quote fees for chains with peers
    fees = lz_block_relay.quote_broadcast_fees(test_eids, 150_000)

    assert len(fees) == len(test_eids)
    for fee in fees:
        assert isinstance(fee, int)

    # Quote fees for chains without peers
    no_peer_eids = [101, 102]
    no_peer_fees = lz_block_relay.quote_broadcast_fees(no_peer_eids, 150_000)

    assert len(no_peer_fees) == len(no_peer_eids)
    for fee in no_peer_fees:
        assert fee == 0  # Should be 0 for chains without peers

    # Quote fees for mixed chains (with and without peers)
    mixed_eids = [30110, 101]
    mixed_fees = lz_block_relay.quote_broadcast_fees(mixed_eids, 150_000)

    assert len(mixed_fees) == len(mixed_eids)
    assert mixed_fees[0] != 0  # Chain with peer should have non-zero fee
    assert mixed_fees[1] == 0  # Chain without peer should have zero fee
