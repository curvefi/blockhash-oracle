import pytest
from web3 import Web3
import rlp


@pytest.mark.gas_profile
def test_default_behavior(block_headers_decoder, block_data, encoded_block_header):
    """Test parent hash extraction from RLP"""
    # Get parent hash via contract
    N = 64
    batch_data = rlp.encode([encoded_block_header] * N)
    # print(batch_data.hex())
    # print(encoded_block_header.hex())
    # print(batch_data.hex())
    n = block_headers_decoder.decode_many_blocks(batch_data)
    print(n)
    assert n == N, "Wrong number of blocks decoded"
