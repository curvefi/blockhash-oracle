# pragma version ~=0.4

"""
@title Block Headers RLP Decoder
@notice Decodes RLP-encoded Ethereum block headers and stores key fields
@dev Extracts block number from RLP and uses it as storage key
"""

# RLP decoding constants
RLP_SHORT_START: constant(uint256) = 128  # 0x80
RLP_LONG_START: constant(uint256) = 183  # 0xb7
RLP_LIST_SHORT_START: constant(uint256) = 192  # 0xc0
RLP_LIST_LONG_START: constant(uint256) = 247  # 0xf7


struct BlockHeader:
    block_hash: bytes32
    parent_hash: bytes32
    state_root: bytes32
    txs_root: bytes32
    timestamp: uint256
    number: uint256


block_headers: public(HashMap[uint256, BlockHeader])


event BlockHeaderDecoded:
    block_number: uint256
    block_hash: bytes32


@deploy
def __init__():
    """
    @notice Initializes the contract
    """
    pass


@view
@external
def calculate_block_hash(encoded_header: Bytes[768]) -> bytes32:
    """
    @notice Calculates block hash from RLP encoded header
    @param encoded_header RLP encoded header data
    @return Block hash
    """
    return keccak256(encoded_header)


@view
@external
def decode_block_headers(encoded_header: Bytes[768]) -> (bytes32, bytes32, uint256, uint256):
    """
    @notice Extracts parent hash from RLP-encoded header
    @param encoded_header RLP encoded header data
    @return Parent hash (first field of block header)
    """
    # First byte tells us about the header structure (we expect list)
    first_byte: uint256 = convert(slice(encoded_header, 0, 1), uint256)
    assert first_byte >= RLP_LIST_SHORT_START, "Not a list"

    # Calculate starting position of data (now we figure out whether the headers are short or long list)
    current_pos: uint256 = 0
    if first_byte < RLP_LIST_LONG_START:  # short list
        current_pos = 1
    else:  # long list
        len_of_len: uint256 = first_byte - RLP_LIST_LONG_START
        current_pos = 1 + len_of_len

    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160  # 0xa0
    # We can now read data of parent hash block (+1 from 0xa0 prefix)
    parent_hash: bytes32 = extract32(
        encoded_header, current_pos + 1, output_type=bytes32
    )  # extract32 defaults to bytes32
    current_pos += 33  # +1 for 0xa0, +32 for data

    # Skip uncle hash (32 bytes with 0xa0 prefix)
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    current_pos += 33

    # Skip miner address (20 bytes with 0x94 prefix)
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 148  # 0x94
    current_pos += 21  # +1 for prefix, +20 for address

    # State root
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    state_root: bytes32 = extract32(encoded_header, current_pos + 1)
    current_pos += 33

    # Skip: tx root, receipt root, logs bloom (256 bytes), difficulty
    # First skip txs root
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    current_pos += 33

    # Skip receipt root
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    current_pos += 33

    # Skip logs bloom
    logs_bloom_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)

    if logs_bloom_prefix < RLP_SHORT_START:  # single byte (like 0)
        current_pos += 1
    elif logs_bloom_prefix < RLP_LONG_START:  # short string
        string_length: uint256 = logs_bloom_prefix - RLP_SHORT_START
        current_pos += 1 + string_length
    else:  # long string (current mainnet case)
        len_of_len: uint256 = logs_bloom_prefix - RLP_LONG_START
        # huge Bytes[768] here because snek inferes largest possible type. thank you snek
        # read_bytes_length: Bytes[768] = slice(encoded_header, current_pos + 1, len_of_len)
        # and then we exploit unsafe typecasting via abi_encode/decode
        data_length: uint256 = convert(
            abi_decode(abi_encode(slice(encoded_header, current_pos + 1, len_of_len)), (Bytes[32])),
            uint256,
        )
        # # Skip: prefix byte + length bytes + actual data
        current_pos += 1 + len_of_len + data_length

    difficulty_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
    if difficulty_prefix < RLP_SHORT_START:
        current_pos += 1  # single byte value
    else:
        diff_len: uint256 = difficulty_prefix - RLP_SHORT_START
        current_pos += 1 + diff_len  # prefix + data

    number_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)

    block_number: uint256 = 0
    if number_prefix < RLP_SHORT_START:
        block_number = number_prefix
        current_pos += 1
    else:
        number_len: uint256 = number_prefix - RLP_SHORT_START
        block_number = convert(
            abi_decode(abi_encode(slice(encoded_header, current_pos + 1, number_len)), (Bytes[32])),
            uint256,
        )
        current_pos += 1 + number_len

    # Skip gas limit
    gas_limit_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
    if gas_limit_prefix < RLP_SHORT_START:
        current_pos += 1
    else:
        gas_limit_len: uint256 = gas_limit_prefix - RLP_SHORT_START
        current_pos += 1 + gas_limit_len

    # Skip gas used
    gas_used_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
    if gas_used_prefix < RLP_SHORT_START:
        current_pos += 1
    else:
        gas_used_len: uint256 = gas_used_prefix - RLP_SHORT_START
        current_pos += 1 + gas_used_len

    # Now extract timestamp
    timestamp_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)

    # Extract timestamp value
    timestamp: uint256 = 0
    if timestamp_prefix < RLP_SHORT_START:
        timestamp = timestamp_prefix
        current_pos += 1
    else:
        timestamp_len: uint256 = timestamp_prefix - RLP_SHORT_START
        timestamp = convert(
            abi_decode(
                abi_encode(slice(encoded_header, current_pos + 1, timestamp_len)),
                (Bytes[32])
            ),
            uint256
        )
        current_pos += 1 + timestamp_len

    return parent_hash, state_root, block_number, timestamp
