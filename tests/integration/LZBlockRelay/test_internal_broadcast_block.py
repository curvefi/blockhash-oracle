"""Test for LZBlockRelay _broadcast_block internal function."""

import pytest
import boa


@pytest.mark.mainnet
def test_broadcast_block(forked_env, lz_block_relay, dev_deployer, block_data):
    """Test broadcasting block hash to multiple chains."""
    # Set up test data
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]

    # Setup peers for broadcasting
    test_eids = [30110, 30111]  # Target chain IDs (arb, opt)
    test_addresses = [boa.env.generate_address(), boa.env.generate_address()]

    with boa.env.prank(dev_deployer):
        # Configure some peers to send messages to
        lz_block_relay.set_peers(test_eids, test_addresses)

        # Make sure we have funds to pay for LZ messages
        boa.env.set_balance(dev_deployer, 10**20)  # 100 ETH
        boa.env.set_balance(lz_block_relay.address, 10**20)  # 100 ETH

    # Prepare the BroadcastTarget struct array
    test_fees = [10**16, 2 * 10**16]  # 0.01 ETH and 0.02 ETH fees
    broadcast_targets = []
    for i in range(len(test_eids)):
        broadcast_targets.append((test_eids[i], test_fees[i]))

    # Add peers to the relay
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers(test_eids, test_addresses)

    # Call the internal broadcast function
    refund_address = dev_deployer

    boa.env.set_balance(dev_deployer, 10 * 10**18)  # 10 ETH
    with boa.env.prank(dev_deployer):
        # Broadcast the block
        lz_block_relay.internal._broadcast_block(
            test_block_number,
            test_block_hash,
            broadcast_targets,
            refund_address,
            value=sum(test_fees),
        )

    # Check events (this will depend on how events are captured in your test environment)
    events = lz_block_relay.get_logs()
    assert any(
        "BlockHashBroadcast" in str(event) for event in events
    ), "BlockHashBroadcast event not emitted"
