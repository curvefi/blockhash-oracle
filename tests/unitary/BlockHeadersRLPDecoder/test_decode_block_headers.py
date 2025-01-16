import pytest
from web3 import Web3


@pytest.mark.gas_profile
def test_default_behavior(block_headers_decoder, block_data, encoded_block_header):
    """Test parent hash extraction from RLP"""
    # Get parent hash via contract
    self_hash, parent_hash, state_root, block_number, timestamp = (
        block_headers_decoder.decode_block_headers(encoded_block_header)
    )

    # Get expected values from block data

    # parent hash
    expected_hash = block_data["parentHash"]  #

    print(f"Extracted parent hash: {parent_hash.hex()}, type: {type(parent_hash)}")
    print(f"Expected parent hash: {expected_hash.hex()}, type: {type(expected_hash)}")
    assert parent_hash == expected_hash, "Parent hash mismatch"

    # state root
    expected_state_root = block_data["stateRoot"]
    print(f"Extracted state root: {state_root.hex()}, type: {type(state_root)}")
    print(f"Expected state root: {expected_state_root.hex()}, type: {type(expected_state_root)}")
    assert state_root == expected_state_root, "State root mismatch"

    # block number
    expected_block_number = block_data["number"]
    print(f"Extracted block number: {block_number}, type: {type(block_number)}")
    print(f"Expected block number: {expected_block_number}, type: {type(expected_block_number)}")
    assert block_number == expected_block_number, "Block number mismatch"

    # timestamp
    expected_timestamp = block_data["timestamp"]
    print(f"Extracted timestamp: {timestamp}, type: {type(timestamp)}")
    print(f"Expected timestamp: {expected_timestamp}, type: {type(expected_timestamp)}")
    assert timestamp == expected_timestamp, "Timestamp mismatch"
