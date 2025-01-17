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
    @return BlockHeader( block_hash, parent_hash, state_root, number, timestamp)
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
                abi_encode(slice(encoded_header, current_pos + 1, timestamp_len)), (Bytes[32])
            ),
            uint256,
        )
        current_pos += 1 + timestamp_len

    return BlockHeader(
        block_hash=keccak256(encoded_header),
        parent_hash=parent_hash,
        state_root=state_root,
        number=block_number,
        timestamp=timestamp,
    )


@view
@external
def decode_block_headers(encoded_header: Bytes[768]) -> BlockHeader:
    return self._decode_block_headers(encoded_header)


@view
@external
def decode_many_blocks(
    encoded_headers: Bytes[65536], forward_direction: bool = True
) -> BlockHeader:
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
            abi_decode(abi_encode(slice(encoded_headers, 1, len_of_len)), (Bytes[32])), uint256
        )
        current_pos = 1 + len_of_len

    end_pos: uint256 = current_pos + total_length
    prev_block: BlockHeader = empty(BlockHeader)
    cur_block: BlockHeader = empty(BlockHeader)

    for blocks_processed: uint256 in range(128):
        # No more than 128 blocks in one call
        if current_pos >= end_pos:
            break


        # Each element is RLP encoded as bytes (0xb9)
        block_prefix: uint256 = convert(slice(encoded_headers, current_pos, 1), uint256)
        assert block_prefix > RLP_LONG_START  # should be 0xb9
        block_len_of_len: uint256 = block_prefix - RLP_LONG_START
        block_length: uint256 = convert(
            abi_decode(
                abi_encode(slice(encoded_headers, current_pos + 1, block_len_of_len)), (Bytes[32])
            ),
            uint256,
        )

        # Skip the 0xb9 wrapping and get the original block RLP
        block_start: uint256 = current_pos + 1 + block_len_of_len
        block_data: Bytes[768] = abi_decode(
            abi_encode(slice(encoded_headers, block_start, block_length)), (Bytes[768])
        )
        cur_block = self._decode_block_headers(block_data)
        current_pos = block_start + block_length

        # Assert chain validity
        if forward_direction:
            if blocks_processed > 0:
                # In direct order parent hash should match previous block hash
                assert cur_block.parent_hash == prev_block.block_hash, "Invalid chain"
        else:
            if blocks_processed > 0:
                # In reverse order parent hash should match next block hash
                assert prev_block.parent_hash == cur_block.block_hash, "Invalid chain"
        prev_block = cur_block
    return cur_block


### More streamlined way that uses util functions below, but eats more gas because passes lots of calldata
@view
@internal
def _decode_block_headers_v2(encoded_header: Bytes[768]) -> BlockHeader:
    """
    @notice Decodes key fields from RLP-encoded Ethereum block header
    @return BlockHeader(block_hash, parent_hash, state_root, number, timestamp)
    """
    # Placeholder variables
    tmp_int: uint256 = 0
    tmp_bytes: bytes32 = empty(bytes32)

    # 1. Parse RLP list header
    current_pos: uint256 = self._read_rlp_list_header(encoded_header)

    # 2. Extract hashes
    parent_hash: bytes32 = empty(bytes32)
    parent_hash, current_pos = self._read_hash32(encoded_header, current_pos)  # parent hash
    tmp_bytes, current_pos = self._read_hash32(encoded_header, current_pos)  # skip uncle hash

    # 3. Skip miner address (20 bytes + 0x94)
    assert convert(slice(encoded_header, current_pos, 1), uint256) == 148
    current_pos += 21

    # 4. Read state root
    state_root: bytes32 = empty(bytes32)
    state_root, current_pos = self._read_hash32(encoded_header, current_pos)

    # 5. Skip transaction and receipt roots
    tmp_bytes, current_pos = self._read_hash32(encoded_header, current_pos)  # skip tx root
    tmp_bytes, current_pos = self._read_hash32(encoded_header, current_pos)  # skip receipt root

    # 6. Skip variable length fields
    current_pos = self._skip_rlp_string(encoded_header, current_pos)  # skip logs bloom

    # 7. Skip difficulty
    tmp_int, current_pos = self._read_rlp_number(encoded_header, current_pos)

    # 8. Read block number
    block_number: uint256 = 0
    block_number, current_pos = self._read_rlp_number(encoded_header, current_pos)

    # 9. Skip gas fields
    tmp_int, current_pos = self._read_rlp_number(encoded_header, current_pos)  # skip gas limit
    tmp_int, current_pos = self._read_rlp_number(encoded_header, current_pos)  # skip gas used

    # 10. Read timestamp
    timestamp: uint256 = 0
    timestamp, current_pos = self._read_rlp_number(encoded_header, current_pos)

    return BlockHeader(
        block_hash=keccak256(encoded_header),
        parent_hash=parent_hash,
        state_root=state_root,
        number=block_number,
        timestamp=timestamp,
    )

@view
@internal
def _read_rlp_list_header(encoded: Bytes[768]) -> uint256:
    """@dev Returns position after list header"""
    first_byte: uint256 = convert(slice(encoded, 0, 1), uint256)
    assert first_byte >= RLP_LIST_SHORT_START, "Not a list"

    if first_byte < RLP_LIST_LONG_START:
        return 1
    else:
        len_of_len: uint256 = first_byte - RLP_LIST_LONG_START
        return 1 + len_of_len


@view
@internal
def _read_hash32(encoded: Bytes[768], pos: uint256) -> (bytes32, uint256):
    """@dev Read 32-byte hash field, returns (hash, next_pos)"""
    assert convert(slice(encoded, pos, 1), uint256) == 160  # 0xa0
    return extract32(encoded, pos + 1), pos + 33


@view
@internal
def _read_rlp_number(encoded: Bytes[768], pos: uint256) -> (uint256, uint256):
    """@dev Read RLP-encoded number, returns (value, next_pos)"""
    prefix: uint256 = convert(slice(encoded, pos, 1), uint256)
    if prefix < RLP_SHORT_START:
        return prefix, pos + 1

    length: uint256 = prefix - RLP_SHORT_START
    value: uint256 = convert(
        abi_decode(abi_encode(slice(encoded, pos + 1, length)), (Bytes[32])), uint256
    )
    return value, pos + 1 + length


@view
@internal
def _skip_rlp_string(encoded: Bytes[768], pos: uint256) -> uint256:
    """@dev Skip RLP string field, returns next_pos"""
    prefix: uint256 = convert(slice(encoded, pos, 1), uint256)
    if prefix < RLP_SHORT_START:
        return pos + 1
    elif prefix < RLP_LONG_START:
        return pos + 1 + (prefix - RLP_SHORT_START)
    else:
        len_of_len: uint256 = prefix - RLP_LONG_START
        data_length: uint256 = convert(
            abi_decode(abi_encode(slice(encoded, pos + 1, len_of_len)), (Bytes[32])), uint256
        )
        return pos + 1 + len_of_len + data_length
