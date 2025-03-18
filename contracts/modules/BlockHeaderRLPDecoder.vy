# pragma version ~=0.4

"""
@title Block Header RLP Decoder Vyper Module
@notice Decodes RLP-encoded Ethereum block header and stores key fields
@dev Extracts block number from RLP and uses it as storage key
"""

################################################################
#                           CONSTANTS                          #
################################################################
# Block header size upper limit
BLOCK_HEADER_SIZE: constant(uint256) = 1024

# RLP decoding constants
RLP_SHORT_START: constant(uint256) = 128  # 0x80
RLP_LONG_START: constant(uint256) = 183  # 0xb7
RLP_LIST_SHORT_START: constant(uint256) = 192  # 0xc0
RLP_LIST_LONG_START: constant(uint256) = 247  # 0xf7


################################################################
#                           STRUCTS                            #
################################################################

struct BlockHeader:
    block_hash: bytes32
    parent_hash: bytes32
    state_root: bytes32
    block_number: uint256
    timestamp: uint256


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__():
    pass


################################################################
#                      EXTERNAL FUNCTIONS                      #
################################################################
# can be exposed optionally, or used in testing
@pure
@external
def calculate_block_hash(encoded_header: Bytes[BLOCK_HEADER_SIZE]) -> bytes32:
    """
    @notice Calculates block hash from RLP encoded header
    @param encoded_header RLP encoded header data
    @return Block hash
    """
    return keccak256(encoded_header)


@pure
@external
def decode_block_header(encoded_header: Bytes[BLOCK_HEADER_SIZE]) -> BlockHeader:
    return self._decode_block_header(encoded_header)


################################################################
#                      CORE FUNCTIONS                          #
################################################################

@pure
@internal
def _decode_block_header(encoded_header: Bytes[BLOCK_HEADER_SIZE]) -> BlockHeader:
    """
    @notice Decodes key fields from RLP-encoded Ethereum block header
    @dev RLP encoding rules:
         - Single byte values (< 0x80) are encoded as themselves
         - Short strings (length < 56) start with 0x80 + length
         - Long strings (length >= 56) start with 0xb7 + length_of_length, followed by length
         - Lists follow similar rules but with 0xc0 and 0xf7 as starting points
         Makes use of utility functions to parse the RLP encoded header,
         and passes entire header to them which is not optimal in terms of gas, but
         makes code more readable.
    @param encoded_header RLP encoded block header
    @return BlockHeader(block_hash, parent_hash, state_root, block_number, timestamp)
    """

    # Placeholder variables
    tmp_int: uint256 = 0
    tmp_bytes: bytes32 = empty(bytes32)

    # Current position in the encoded header
    current_pos: uint256 = 0

    # 1. Skip RLP list length
    current_pos = self._skip_rlp_list(encoded_header, current_pos)

    # 2. Extract hashes
    parent_hash: bytes32 = empty(bytes32)
    parent_hash, current_pos = self._read_hash32(encoded_header, current_pos)  # parent hash
    tmp_bytes, current_pos = self._read_hash32(encoded_header, current_pos)  # skip uncle hash

    # 3. Skip miner address (20 bytes + 0x94)
    assert convert(slice(encoded_header, current_pos, 1), bytes1) == 0x94
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
        block_number=block_number,
        timestamp=timestamp,
    )


################################################################
#                      UTILITY FUNCTIONS                       #
################################################################

@pure
@internal
def _skip_rlp_list(encoded: Bytes[BLOCK_HEADER_SIZE], pos: uint256) -> uint256:
    """@dev Returns position after list header"""
    first_byte: uint256 = convert(slice(encoded, 0, 1), uint256)
    assert first_byte >= RLP_LIST_SHORT_START, "Not a list"
    if first_byte <= RLP_LIST_LONG_START:
        return pos + 1
    else:
        return pos + 1 + (first_byte - RLP_LIST_LONG_START)


@pure
@internal
def _skip_rlp_string(encoded: Bytes[BLOCK_HEADER_SIZE], pos: uint256) -> uint256:
    """@dev Skip RLP string field, returns next_pos"""
    prefix: uint256 = convert(slice(encoded, pos, 1), uint256)
    if prefix < RLP_SHORT_START:
        return pos + 1
    elif prefix <= RLP_LONG_START:
        return pos + 1 + (prefix - RLP_SHORT_START)
    else:
        # Sanity check: ensure this is a string, not a list
        assert prefix < RLP_LIST_SHORT_START, "Expected string, found list prefix"

        len_of_len: uint256 = prefix - RLP_LONG_START
        data_length: uint256 = convert(
            abi_decode(abi_encode(slice(encoded, pos + 1, len_of_len)), (Bytes[32])), uint256
        )
        return pos + 1 + len_of_len + data_length


@pure
@internal
def _read_hash32(encoded: Bytes[BLOCK_HEADER_SIZE], pos: uint256) -> (bytes32, uint256):
    """@dev Read 32-byte hash field, returns (hash, next_pos)"""
    assert convert(slice(encoded, pos, 1), uint256) == 160  # RLP_SHORT_START + 32
    return extract32(encoded, pos + 1), pos + 33


@pure
@internal
def _read_rlp_number(encoded: Bytes[BLOCK_HEADER_SIZE], pos: uint256) -> (uint256, uint256):
    """@dev Read RLP-encoded number, returns (value, next_pos)"""
    prefix: uint256 = convert(slice(encoded, pos, 1), uint256)
    if prefix < RLP_SHORT_START:
        return prefix, pos + 1

    # Sanity check: ensure this is a short string (not a long string or list)
    assert prefix <= RLP_LONG_START, "Invalid RLP number encoding"

    length: uint256 = prefix - RLP_SHORT_START
    value: uint256 = convert(
        abi_decode(abi_encode(slice(encoded, pos + 1, length)), (Bytes[32])), uint256
    )
    # abi_decode(abi_encode(bytesA), bytesB) is needed to unsafe cast bytesA to bytesB
    return value, pos + 1 + length
