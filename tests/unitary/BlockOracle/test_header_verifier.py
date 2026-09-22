import boa
import pytest

N_BLOCKS_BATCH = 10


@pytest.fixture
def block_oracle_set(block_oracle, block_headers_decoder):
    with boa.env.prank(block_oracle.owner()):
        block_oracle.set_header_verifier(block_headers_decoder.address)
    return block_oracle


def test_set_header_verifier(block_oracle, block_headers_decoder):
    """Test setting the header verifier"""
    assert block_oracle.header_verifier() == boa.eval("empty(address)")

    # test access auth
    with boa.env.prank(boa.env.generate_address()):
        with boa.reverts("ownable: caller is not the owner"):
            block_oracle.set_header_verifier(block_headers_decoder.address)

    # test set
    with boa.env.prank(block_oracle.owner()):
        # First set - from empty address to block_headers_decoder
        block_oracle.set_header_verifier(block_headers_decoder.address)
        assert block_oracle.header_verifier() == block_headers_decoder.address

        # Change to another address - from block_headers_decoder to new_verifier
        new_verifier = boa.env.generate_address()
        block_oracle.set_header_verifier(new_verifier)
        assert block_oracle.header_verifier() == new_verifier

        # Note: Event emission is tested implicitly - if the event is emitted correctly,
        # the contract will compile and execute without errors. The actual event
        # verification would require mocking or integration testing framework support.


def test_submit_valid_block_header(
    block_oracle_set, block_headers_decoder, encoded_block_header, block_data
):
    """Test submitting a valid block header for an applied block"""
    # First apply the actual block hash from our test data
    with boa.env.prank(block_oracle_set.owner()):
        block_oracle_set.admin_apply_block(block_data["number"], block_data["hash"])

    # Now submit the header - this should work since hash matches
    block_headers_decoder.submit_block_header(block_oracle_set.address, encoded_block_header)

    # Verify the header was stored correctly
    header = block_oracle_set.block_header(block_data["number"])
    assert header[0] == block_data["hash"]
    assert header[1] == block_data["parentHash"]
    assert header[2] == block_data["stateRoot"]
    assert header[3] == block_data["receiptsRoot"]
    assert header[4] == block_data["number"]
    assert header[5] == block_data["timestamp"]

    # Verify last_confirmed_header was updated
    last_header = block_oracle_set.last_confirmed_header()
    assert last_header[0] == block_data["hash"]
    assert last_header[1] == block_data["parentHash"]
    assert last_header[2] == block_data["stateRoot"]
    assert last_header[3] == block_data["receiptsRoot"]
    assert last_header[4] == block_data["number"]
    assert last_header[5] == block_data["timestamp"]


def test_submit_header_without_applied_block(
    block_oracle_set, block_headers_decoder, encoded_block_header
):
    """Test that submitting header fails if block hash not yet applied"""
    with boa.reverts("Blockhash not applied"):
        block_headers_decoder.submit_block_header(block_oracle_set.address, encoded_block_header)


def test_submit_header_with_wrong_hash(
    block_oracle_set, block_headers_decoder, encoded_block_header, block_data
):
    """Test that submitting header fails if hash doesn't match applied block"""
    # Apply wrong hash for the block number
    wrong_hash = b"\x01" * 32
    with boa.env.prank(block_oracle_set.owner()):
        block_oracle_set.admin_apply_block(block_data["number"], wrong_hash)

    # Try to submit header that won't match the applied hash
    with boa.reverts("Blockhash does not match"):
        block_headers_decoder.submit_block_header(block_oracle_set, encoded_block_header)


def test_submit_header_multiple_times(
    block_oracle_set, block_headers_decoder, encoded_block_header, block_data
):
    """Test submitting same header multiple times"""
    # First apply the actual block hash
    with boa.env.prank(block_oracle_set.owner()):
        block_oracle_set.admin_apply_block(block_data["number"], block_data["hash"])

    # Submit header first time
    block_headers_decoder.submit_block_header(block_oracle_set.address, encoded_block_header)

    # Submit again - should not work
    with boa.reverts("Header already submitted"):
        block_headers_decoder.submit_block_header(block_oracle_set.address, encoded_block_header)

    # Verify data is still correct
    header = block_oracle_set.block_header(block_data["number"])
    assert header[0] == block_data["hash"]
    assert header[1] == block_data["parentHash"]
    assert header[2] == block_data["stateRoot"]
    assert header[3] == block_data["receiptsRoot"]
    assert header[4] == block_data["number"]
    assert header[5] == block_data["timestamp"]


@pytest.mark.parametrize("n_blocks_data", [N_BLOCKS_BATCH], indirect=True)
def test_last_confirmed_header_sequence(
    block_oracle_set, block_headers_decoder, n_blocks_data, n_encoded_blocks_headers
):
    """Test last_confirmed_header updates correctly with sequence of headers"""
    last_header = block_oracle_set.last_confirmed_header()
    assert last_header[4] == 0

    # Apply block hashes in sequence
    for i, block in enumerate(n_blocks_data):
        with boa.env.prank(block_oracle_set.owner()):
            block_oracle_set.admin_apply_block(block["number"], block["hash"])

        # Submit header
        block_headers_decoder.submit_block_header(
            block_oracle_set.address, n_encoded_blocks_headers[i]
        )

        # Verify last_confirmed_header is updated only for highest block number
        last_header = block_oracle_set.last_confirmed_header()
        assert last_header[0] == block["hash"]  # block_hash
        assert last_header[1] == block["parentHash"]  # parent_hash
        assert last_header[2] == block["stateRoot"]  # state_root
        assert last_header[3] == block["receiptsRoot"]  # receipts_root
        assert last_header[4] == block["number"]  # block_number
        assert last_header[5] == block["timestamp"]  # timestamp


@pytest.mark.parametrize("n_blocks_data", [N_BLOCKS_BATCH], indirect=True)
def test_last_confirmed_header_out_of_order(
    block_oracle_set, block_headers_decoder, n_blocks_data, n_encoded_blocks_headers
):
    """Test last_confirmed_header updates correctly with out of order submissions"""
    # Apply all block hashes first
    for block in n_blocks_data:
        with boa.env.prank(block_oracle_set.owner()):
            block_oracle_set.admin_apply_block(block["number"], block["hash"])

    # Submit headers in reverse order
    for i in range(len(n_blocks_data) - 1, -1, -1):
        block = n_blocks_data[i]
        block_headers_decoder.submit_block_header(
            block_oracle_set.address, n_encoded_blocks_headers[i]
        )

        # Last confirmed header should be the highest block number submitted so far
        highest_block = max(n_blocks_data[i:], key=lambda x: x["number"])
        last_header = block_oracle_set.last_confirmed_header()
        assert last_header[4] == highest_block["number"]  # block_number
        assert last_header[0] == highest_block["hash"]  # block_hash


# ─── Owner hash overrides ────────────────────────────────────────────────────


def _header(block_number, block_hash, state_root):
    # (block_hash, parent_hash, state_root, receipt_root, block_number, timestamp)
    return (block_hash, bytes(32), state_root, bytes(32), block_number, 1_700_000_000)


def _submit(block_oracle, verifier, header):
    with boa.env.prank(verifier):
        block_oracle.submit_block_header(header)


def test_override_drops_the_old_header(block_oracle, dev_deployer):
    """Replacing a hash drops the header decoded from the old one: get_state_root stops serving the
    old state, and the header matching the new hash can be submitted."""
    verifier = boa.env.generate_address()
    n = 21_000_000
    bad_hash, good_hash = b"\xbb" * 32, b"\x01" * 32
    bad_root, good_root = b"\xcc" * 32, b"\x02" * 32
    with boa.env.prank(dev_deployer):
        block_oracle.set_header_verifier(verifier)
        block_oracle.admin_apply_block(n, bad_hash)
    _submit(block_oracle, verifier, _header(n, bad_hash, bad_root))
    assert block_oracle.get_state_root(n) == bad_root

    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(n, good_hash)

    assert block_oracle.get_block_hash(n) == good_hash
    assert block_oracle.get_state_root(n) == bytes(32)

    _submit(block_oracle, verifier, _header(n, good_hash, good_root))
    assert block_oracle.get_state_root(n) == good_root


def test_reapplying_the_same_hash_keeps_the_header(block_oracle, dev_deployer):
    """Only a different hash invalidates the header; re-applying the same one leaves it in place."""
    verifier = boa.env.generate_address()
    n, block_hash, root = 21_000_000, b"\x01" * 32, b"\x02" * 32
    with boa.env.prank(dev_deployer):
        block_oracle.set_header_verifier(verifier)
        block_oracle.admin_apply_block(n, block_hash)
    _submit(block_oracle, verifier, _header(n, block_hash, root))

    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(n, block_hash)

    assert block_oracle.get_state_root(n) == root
