import boa


def test_submit_valid_block_header(block_oracle, encoded_block_header, block_data):
    """Test submitting a valid block header for an applied block"""
    # First apply the actual block hash from our test data
    with boa.env.prank(block_oracle.owner()):
        block_oracle.admin_apply_block(block_data["number"], block_data["hash"])

    # Now submit the header - this should work since hash matches
    block_oracle.submit_block_header(encoded_block_header)

    # Verify the header was stored correctly
    header = block_oracle.block_header(block_data["number"])
    assert header[0] == block_data["hash"]
    assert header[1] == block_data["parentHash"]
    assert header[2] == block_data["stateRoot"]
    assert header[3] == block_data["number"]
    assert header[4] == block_data["timestamp"]


def test_submit_header_without_applied_block(block_oracle, encoded_block_header):
    """Test that submitting header fails if block hash not yet applied"""
    with boa.reverts("Blockhash not applied"):
        block_oracle.submit_block_header(encoded_block_header)


def test_submit_header_with_wrong_hash(block_oracle, encoded_block_header, block_data):
    """Test that submitting header fails if hash doesn't match applied block"""
    # Apply wrong hash for the block number
    wrong_hash = b"\x01" * 32
    with boa.env.prank(block_oracle.owner()):
        block_oracle.admin_apply_block(block_data["number"], wrong_hash)

    # Try to submit header that won't match the applied hash
    with boa.reverts("Blockhash does not match"):
        block_oracle.submit_block_header(encoded_block_header)


def test_submit_header_multiple_times(block_oracle, encoded_block_header, block_data):
    """Test submitting same header multiple times"""
    # First apply the actual block hash
    with boa.env.prank(block_oracle.owner()):
        block_oracle.admin_apply_block(block_data["number"], block_data["hash"])

    # Submit header first time
    block_oracle.submit_block_header(encoded_block_header)

    # Submit again - should work but just overwrite same data
    block_oracle.submit_block_header(encoded_block_header)

    # Verify data is still correct
    header = block_oracle.block_header(block_data["number"])
    assert header[0] == block_data["hash"]
    assert header[1] == block_data["parentHash"]
    assert header[2] == block_data["stateRoot"]
    assert header[3] == block_data["number"]
    assert header[4] == block_data["timestamp"]
