from web3 import Web3


def test_default_behavior(block_headers_decoder_module, block_data, encoded_block_header):
    """Test that block hash calculation matches web3's hash"""

    # Calculate hash via contract
    contract_hash = block_headers_decoder_module.calculate_block_hash(encoded_block_header)

    # Calculate expected hash
    expected_hash = Web3.keccak(encoded_block_header)

    print(f"Contract hash: {contract_hash.hex()}")
    print(f"Expected hash: {expected_hash.hex()}")
    print(f"Block hash: {block_data['hash'].hex()}")
    print(f"Block number: {block_data['number']}")

    assert block_data["hash"] == expected_hash, "Wrong expected hash"
    assert contract_hash == expected_hash, "Wrong contract hash"
