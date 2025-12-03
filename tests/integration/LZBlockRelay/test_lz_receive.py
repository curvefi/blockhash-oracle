"""Test for LZBlockRelay lzReceive function."""

import pytest
import boa

from conftest import LZ_READ_CHANNEL, LZ_EID, LZ_ENDPOINT


@pytest.mark.mainnet
def test_lz_receive_read_response(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """Test handling a read response in lzReceive."""
    # Setup the relay with all needed configurations
    with boa.env.prank(dev_deployer):
        # Set block oracle
        lz_block_relay.set_block_oracle(block_oracle.address)

        # Setup read config - enable read functionality
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

        # Add the relay as a committer to the oracle
        block_oracle.add_committer(lz_block_relay.address, True)

        # Add funds for tests
        boa.env.set_balance(dev_deployer, 10**20)  # 100 ETH
        boa.env.set_balance(lz_block_relay.address, 10**20)  # 100 ETH

    # Create an Origin struct for a message from the read channel
    origin = (LZ_READ_CHANNEL, boa.eval(f"convert({lz_block_relay.address}, bytes32)"), 0)
    guid = bytes(32)  # Empty bytes32 for test

    # Create a message with block data
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]
    message = boa.util.abi.abi_encode("(uint256,bytes32)", (test_block_number, test_block_hash))

    assert lz_block_relay._storage.received_blocks.get() == {}

    # Call lzReceive directly (not from the endpoint, must revert)
    with boa.reverts("OApp: only endpoint"):
        with boa.env.prank(dev_deployer):  # Using deployer as the endpoint for testing
            lz_block_relay.lzReceive(origin, guid, message, dev_deployer, b"")

    # Call lzReceive from the endpoint
    with boa.env.prank(LZ_ENDPOINT):
        lz_block_relay.lzReceive(origin, guid, message, dev_deployer, b"")

    # Check if block was stored in received_blocks
    assert lz_block_relay._storage.received_blocks.get()[test_block_number] == test_block_hash

    # Check if block was committed to the oracle
    assert (
        block_oracle.committer_votes(lz_block_relay.address, test_block_number) == test_block_hash
    )


@pytest.mark.mainnet
def test_lz_receive_regular_message(
    forked_env, lz_block_relay, block_oracle, dev_deployer, block_data
):
    """Test handling a regular message in lzReceive."""
    # Setup the relay
    with boa.env.prank(dev_deployer):
        # Set block oracle
        lz_block_relay.set_block_oracle(block_oracle.address)

        # Add the relay as a committer to the oracle
        block_oracle.add_committer(lz_block_relay.address, True)

    # Create Origin struct from a different EID (not read channel)
    different_eid = 999
    origin = (different_eid, boa.eval(f"convert({lz_block_relay.address}, bytes32)"), 0)
    guid = bytes(32)  # Empty bytes32 for test

    # Create a message with block data
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]
    message = boa.util.abi.abi_encode("(uint256,bytes32)", (test_block_number, test_block_hash))

    # Add peer for the source chain to allow the message
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_peers([different_eid], [lz_block_relay.address])

    # Call lzReceive directly (as if from the endpoint)
    with boa.env.prank(LZ_ENDPOINT):
        lz_block_relay.lzReceive(origin, guid, message, dev_deployer, b"")

    # Regular messages don't store in received_blocks, but they should commit to oracle
    # Check the block oracle for the committed block
    assert (
        block_oracle.committer_votes(lz_block_relay.address, test_block_number) == test_block_hash
    )

    # Also verify it was NOT stored in received_blocks
    assert lz_block_relay._storage.received_blocks.get() == {}


@pytest.mark.mainnet
def test_lz_receive_read_response_with_broadcast(
    forked_env, lz_block_relay, block_oracle, mainnet_block_view, dev_deployer, block_data
):
    """Test handling a read response that should trigger broadcast."""
    # Setup the relay with all needed configurations
    with boa.env.prank(dev_deployer):
        # Set block oracle
        lz_block_relay.set_block_oracle(block_oracle.address)

        # Setup read config - enable read functionality
        lz_block_relay.set_read_config(True, LZ_READ_CHANNEL, LZ_EID, mainnet_block_view.address)

        # Add the relay as a committer to the oracle
        block_oracle.add_committer(lz_block_relay.address, True)

        # Add funds for tests
        boa.env.set_balance(dev_deployer, 10**20)  # 100 ETH
        boa.env.set_balance(LZ_ENDPOINT, 10**20)  # 100 ETH

        # Setup peers for broadcasting
        test_eids = [30110, 30111]
        test_addresses = [boa.env.generate_address(), boa.env.generate_address()]
        lz_block_relay.set_peers(test_eids, test_addresses)

    # Create an Origin struct for a message from the read channel
    origin = (LZ_READ_CHANNEL, boa.eval(f"convert({lz_block_relay.address}, bytes32)"), 0)

    # emulate request_block_hash flow
    broadcast_fees = lz_block_relay.quote_broadcast_fees(test_eids, 150_000)
    broadcast_fees_doubled = [fee * 2 for fee in broadcast_fees]
    lz_read_gas_limit = 100_000
    read_fee = lz_block_relay.quote_read_fee(lz_read_gas_limit, sum(broadcast_fees_doubled))
    with boa.env.prank(dev_deployer):
        lz_block_relay.request_block_hash(
            test_eids, broadcast_fees_doubled, 150_000, lz_read_gas_limit, 0, value=read_fee
        )
    guid = list(lz_block_relay._storage.broadcast_data.get().keys())[0]

    # Create a message with block data
    test_block_number = block_data["number"]
    test_block_hash = block_data["hash"]
    message = boa.util.abi.abi_encode("(uint256,bytes32)", (test_block_number, test_block_hash))
    relay_bal_before = boa.env.get_balance(lz_block_relay.address)
    deployer_bal_before = boa.env.get_balance(dev_deployer)
    # Call lzReceive directly with value to cover broadcast fees
    with boa.env.prank(LZ_ENDPOINT):
        lz_block_relay.lzReceive(
            origin, guid, message, dev_deployer, b"", value=sum(broadcast_fees_doubled)
        )
    relay_bal_after = boa.env.get_balance(lz_block_relay.address)
    deployer_bal_after = boa.env.get_balance(dev_deployer)
    assert relay_bal_after == relay_bal_before  # no refund to relay
    assert deployer_bal_after > deployer_bal_before  # refund to deployer
    refund_amount = deployer_bal_after - deployer_bal_before
    fee_overpaid = sum(broadcast_fees_doubled) - sum(broadcast_fees)
    assert refund_amount == fee_overpaid
    # Check that event was emitted for broadcast
    events = lz_block_relay.get_logs()
    assert any(
        "BlockHashBroadcast" in str(event) for event in events
    ), "BlockHashBroadcast event not emitted"
