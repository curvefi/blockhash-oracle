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
    number: uint256
    timestamp: uint256



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
@internal
def _decode_block_headers(encoded_header: Bytes[768]) -> BlockHeader:
    """
    @notice Decodes key fields from RLP-encoded Ethereum block header
    @dev RLP encoding rules:
         - Single byte values (< 0x80) are encoded as themselves
         - Short strings (length < 56) start with 0x80 + length
         - Long strings (length >= 56) start with 0xb7 + length_of_length, followed by length
         - Lists follow similar rules but with 0xc0 and 0xf7 as starting points
    @param encoded_header RLP encoded block header
    @return (parent_hash, state_root, block_number, timestamp)
    """
    # 1. Parse RLP list header
    first_byte: uint256 = convert(slice(encoded_header, 0, 1), uint256)
    assert first_byte >= RLP_LIST_SHORT_START, "Not a list"

    current_pos: uint256 = 0
    if first_byte < RLP_LIST_LONG_START:  # short list
        current_pos = 1
    else:  # long list, next N bytes encode the length
        len_of_len: uint256 = first_byte - RLP_LIST_LONG_START
        current_pos = 1 + len_of_len

    # 2. Extract fixed-length fields
    # Parent hash: 32 bytes prefixed with 0xa0
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160  # 0xa0
    parent_hash: bytes32 = extract32(encoded_header, current_pos + 1, output_type=bytes32)
    current_pos += 33  # prefix + data

    # Skip uncle hash (32 bytes + 0xa0)
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    current_pos += 33

    # Skip miner address (20 bytes + 0x94)
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 148  # 0x94
    current_pos += 21

    # State root: 32 bytes prefixed with 0xa0
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    state_root: bytes32 = extract32(encoded_header, current_pos + 1)
    current_pos += 33

    # 3. Skip more fixed-length fields
    # Skip transaction root and receipt root (each 32 bytes + 0xa0)
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    current_pos += 33
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 160
    current_pos += 33

    # 4. Handle variable-length fields
    # Skip logs bloom - can be long string or (after EIP-7668) small value
    logs_bloom_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
    if logs_bloom_prefix < RLP_SHORT_START:  # single byte
        current_pos += 1
    elif logs_bloom_prefix < RLP_LONG_START:  # short string
        string_length: uint256 = logs_bloom_prefix - RLP_SHORT_START
        current_pos += 1 + string_length
    else:  # long string (pre EIP-7668 case)
        len_of_len: uint256 = logs_bloom_prefix - RLP_LONG_START
        data_length: uint256 = convert(
            abi_decode(abi_encode(slice(encoded_header, current_pos + 1, len_of_len)), (Bytes[32])),
            uint256,
        )
        current_pos += 1 + len_of_len + data_length

    # Skip difficulty - usually small but handle variable length
    difficulty_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
    if difficulty_prefix < RLP_SHORT_START:
        current_pos += 1
    else:
        diff_len: uint256 = difficulty_prefix - RLP_SHORT_START
        current_pos += 1 + diff_len

    # 5. Extract block number
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

    # 6. Skip gas fields
    # Skip gas limit and gas used - both variable length numbers
    for i: uint256 in range(2):  # handle both fields same way
        prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
        if prefix < RLP_SHORT_START:
            current_pos += 1
        else:
            length: uint256 = prefix - RLP_SHORT_START
            current_pos += 1 + length

    # 7. Extract timestamp
    timestamp_prefix: uint256 = convert(slice(encoded_header, current_pos, 1), uint256)
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

    return BlockHeader(
        block_hash=keccak256(encoded_header),
        parent_hash=parent_hash,
        state_root=state_root,
        number=block_number,
        timestamp=timestamp
    )

@view
@external
def decode_block_headers(encoded_header: Bytes[768])-> BlockHeader:
    return self._decode_block_headers(encoded_header)

@view
@external
def decode_many_blocks(encoded_headers: Bytes[49152]) -> uint256:
    first_byte: uint256 = convert(slice(encoded_headers, 0, 1), uint256)
    assert first_byte >= RLP_LIST_SHORT_START, "Not a list"
    
    current_pos: uint256 = 0
    total_length: uint256 = 0
    
    if first_byte < RLP_LIST_LONG_START:
        current_pos = 1
        total_length = first_byte - RLP_LIST_SHORT_START
    else:
        len_of_len: uint256 = first_byte - RLP_LIST_LONG_START
        total_length = convert(
            abi_decode(abi_encode(slice(encoded_headers, 1, len_of_len)), (Bytes[32])),
            uint256
        )
        current_pos = 1 + len_of_len
    
    blocks_processed: uint256 = 0
    end_pos: uint256 = current_pos + total_length

    for i: uint256 in range(128):
        if current_pos >= end_pos:
            break

        # Each element is RLP encoded as bytes (0xb9)
        block_prefix: uint256 = convert(slice(encoded_headers, current_pos, 1), uint256)
        assert block_prefix > RLP_LONG_START  # should be 0xb9
        block_len_of_len: uint256 = block_prefix - RLP_LONG_START
        block_length: uint256 = convert(
            abi_decode(abi_encode(slice(encoded_headers, current_pos + 1, block_len_of_len)), (Bytes[32])),
            uint256
        )
        
        # Skip the 0xb9 wrapping and get the original block RLP
        block_start: uint256 = current_pos + 1 + block_len_of_len
        block_data: Bytes[768] = abi_decode(
            abi_encode(slice(encoded_headers, block_start, block_length)),
            (Bytes[768])
        )
        
        self._decode_block_headers(block_data)
        current_pos = block_start + block_length
        blocks_processed += 1
    
    return blocks_processed