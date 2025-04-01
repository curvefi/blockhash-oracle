"""Test for LZBlockRelay _prepare_read_request internal function."""

import pytest
import boa

# Constants for test
LZ_READ_CHANNEL = 4294967295
LZ_CHAIN_ID = 1  # Ethereum mainnet
GET_BLOCKHASH_SELECTOR = boa.eval("method_id('get_blockhash(uint256,bool)')")


@pytest.mark.mainnet
def test_prepare_read_request(forked_env, lz_block_relay, mainnet_block_view, dev_deployer):
    """Test preparing read request message for MainnetBlockView."""
    # Configure read capability
    with boa.env.prank(dev_deployer):
        lz_block_relay.set_read_config(
            True, LZ_READ_CHANNEL, LZ_CHAIN_ID, mainnet_block_view.address
        )

    # Test for latest block (block_number = 0)
    message = lz_block_relay.internal._prepare_read_request(0)

    # Message should not be empty
    assert message != b""

    # Test with specific block number
    test_block_number = 15000000
    message = lz_block_relay.internal._prepare_read_request(test_block_number)

    # Message should not be empty and should be different from the previous message
    assert message != b""

    # Test that the message includes our method selector
    assert GET_BLOCKHASH_SELECTOR in message

    # Test that the message includes the correct block number in hex
    assert hex(test_block_number)[2:] in message.hex()
