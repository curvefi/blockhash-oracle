"""Test for LZBlockRelay request_block_hash function."""

import pytest
import boa

from conftest import LZ_READ_CHANNEL, LZ_EID


@pytest.mark.mainnet
def test_request_block_hash(forked_env, lz_block_relay, dev_deployer, mainnet_block_view):
    """Test requesting a block hash from mainnet."""
    # Generate a user address
    user = boa.env.generate_address()
    boa.env.set_balance(user, 10**20)  # 100 ETH

    # Setup peers for testing
    test_eids = [30110, 30111, 30112]
    test_addresses = [
        boa.env.generate_address(),
        boa.env.generate_address(),
        boa.env.generate_address(),
    ]

    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers(test_eids, test_addresses)

    # Get broadcast fees
    lz_read_gas_limit = 100_000

    # Should fail if read not enabled
    with boa.env.prank(user):
        with boa.reverts("Read not enabled"):
            lz_block_relay.request_block_hash(test_eids, [10**16, 10**16], lz_read_gas_limit)

    # Enable read functionality
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

    # cost to broadcast to all targets
    broadcast_fees = lz_block_relay.quote_broadcast_fees(test_eids)
    # cost to read from mainnet (including broadcast fees)
    read_fee = lz_block_relay.quote_read_fee(lz_read_gas_limit, sum(broadcast_fees))

    # Should fail with mismatched array lengths
    with boa.env.prank(user):
        with boa.reverts("Length mismatch"):
            lz_block_relay.request_block_hash(test_eids, broadcast_fees[:1], lz_read_gas_limit)

    # Valid request (Note: In test environment, this will not actually send a message)
    with boa.env.prank(user):
        lz_block_relay.request_block_hash(
            test_eids, broadcast_fees, lz_read_gas_limit, value=read_fee
        )

    # A real implementation would also verify:
    # 1. The correct message was sent to LZ endpoint
    # 2. The broadcast targets were stored correctly
    # 3. ETH was properly distributed (read fee to LZ, remainder stays in contract)
