import pytest
import rlp

N_BLOCKS_PROVE = 2


@pytest.mark.gas_profile
@pytest.mark.parametrize("n_blocks_data", [N_BLOCKS_PROVE], indirect=True)
def test_default_behavior(
    block_headers_decoder, n_blocks_data, n_encoded_blocks_headers, encoded_block_header
):
    """Test RLP block chain decoding"""
    # n_blocks_data and n_encoded_blocks_headers are backwards ordered chain of blocks
    # Backwards decoding
    call_param_rlp = rlp.encode(n_encoded_blocks_headers)
    block_hash, parent_hash, state_root, number, timestamp = (
        block_headers_decoder.decode_many_blocks(call_param_rlp, False)
    )
    # block_hash, parent_hash, state_root, number, timestamp
    print(f"Extracted hash: {block_hash.hex()}")
    print(f"Expected hash: {n_blocks_data[-1]["hash"].hex()}")
    assert block_hash == n_blocks_data[-1]["hash"], "Hash mismatch"

    # # Forwards decoding
    call_param_rlp = rlp.encode(n_encoded_blocks_headers[::-1])
    block_hash, parent_hash, state_root, number, timestamp = (
        block_headers_decoder.decode_many_blocks(call_param_rlp, True)
    )
    print(f"Extracted hash: {block_hash.hex()}")
    print(f"Expected hash: {n_blocks_data[0]['hash'].hex()}")
    assert block_hash == n_blocks_data[0]["hash"], "Hash mismatch"
