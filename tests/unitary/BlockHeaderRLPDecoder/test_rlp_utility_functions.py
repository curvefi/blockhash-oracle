import binascii

# Constants from the contract for testing
RLP_SHORT_START = 128  # 0x80
RLP_LONG_START = 183  # 0xb7
RLP_LIST_SHORT_START = 192  # 0xc0
RLP_LIST_LONG_START = 247  # 0xf7


def test_skip_rlp_list_header(block_headers_decoder):
    """
    Test _skip_rlp_list_header function with various inputs including boundary conditions
    """
    # Test case 1: Short list (below boundary)
    short_list_header = bytes([0xC0])  # Shortest possible list encoding
    current_pos = 0
    result = block_headers_decoder.eval(
        f"self._skip_rlp_list_header({short_list_header}, {current_pos})"
    )
    assert result == 1, "Short list header should return position 1"

    # Test case 2: Short list (middle of range)
    mid_short_list = bytes([0xE0])  # Some value between 0xc0 and 0xf7
    current_pos = 0
    result = block_headers_decoder.eval(
        f"self._skip_rlp_list_header({mid_short_list}, {current_pos})"
    )
    assert result == 1, "Short list header should return position 1"

    # Test case 3: BOUNDARY CASE - exactly at RLP_LIST_LONG_START (0xf7)
    boundary_case = bytes([0xF7])
    current_pos = 0
    result = block_headers_decoder.eval(
        f"self._skip_rlp_list_header({boundary_case}, {current_pos})"
    )
    assert result == 1, "Boundary case (0xf7) should be treated as short list"

    # Test case 4: Long list header (0xf8) with 1 byte length
    long_list_header = bytes([0xF8, 0x80])  # List with length field of 1 byte
    current_pos = 0
    result = block_headers_decoder.eval(
        f"self._skip_rlp_list_header({long_list_header}, {current_pos})"
    )
    assert result == 2, "Long list header (0xf8) should return position 2"

    # Test case 5: Long list header (0xf9) with 2 byte length
    very_long_list = bytes([0xF9, 0x01, 0x00])  # List with length field of 2 bytes
    current_pos = 0
    result = block_headers_decoder.eval(
        f"self._skip_rlp_list_header({very_long_list}, {current_pos})"
    )
    assert result == 3, "Long list header (0xf9) should return position 3"


def test_skip_rlp_string(block_headers_decoder):
    """
    Test _skip_rlp_string function with various inputs including boundary conditions
    """
    # Test case 1: Single byte (< 0x80)
    single_byte = bytes([0x7F])
    result = block_headers_decoder.eval(f"self._skip_rlp_string({single_byte}, 0)")
    assert result == 1, "Single byte string should advance position by 1"

    # Test case 2: Short string (length 1)
    short_string = bytes([0x81, 0x61])  # "a"
    result = block_headers_decoder.eval(f"self._skip_rlp_string({short_string}, 0)")
    assert result == 2, "Short string of length 1 should advance position by 2"

    # Test case 3: Short string (max length 55)
    max_short_string = bytes([0xB6]) + bytes([0x61] * 54)  # 54 "a"s
    result = block_headers_decoder.eval(f"self._skip_rlp_string({max_short_string}, 0)")
    assert result == 55, "Max short string (prefix 0xb6) should advance to pos 55"

    # Test case 4: BOUNDARY CASE - exactly at RLP_LONG_START (0xb7)
    boundary_case = bytes([0xB7]) + bytes([0x61] * 55)  # 55 "a"s
    result = block_headers_decoder.eval(f"self._skip_rlp_string({boundary_case}, 0)")
    assert result == 56, "Boundary case (0xb7) should be treated as short string"

    # Test case 5: Long string with 1-byte length field
    long_string_header = bytes([0xB8, 0x0A]) + bytes(
        [0x61] * 10
    )  # String of length 10 with long encoding
    result = block_headers_decoder.eval(f"self._skip_rlp_string({long_string_header}, 0)")
    assert result == 12, "Long string with 1-byte length field should advance pos by 2 + length"


def test_read_rlp_number(block_headers_decoder):
    """
    Test _read_rlp_number function with various inputs
    """
    # Test case 1: Single byte number
    single_byte = bytes([0x7F])
    value, next_pos = block_headers_decoder.eval(f"self._read_rlp_number({single_byte}, 0)")
    assert value == 0x7F, "Should decode single byte number correctly"
    assert next_pos == 1, "Should advance position by 1"

    # Test case 2: Short encoded number (1 byte)
    short_number = bytes([0x81, 0xFF])  # 255 encoded as short string
    value, next_pos = block_headers_decoder.eval(f"self._read_rlp_number({short_number}, 0)")
    assert value == 0xFF, "Should decode short encoded number correctly"
    assert next_pos == 2, "Should advance position by 2"

    # Test case 3: Longer encoded number (2 bytes)
    two_byte_number = bytes([0x82, 0x01, 0x00])  # 256 encoded as short string
    value, next_pos = block_headers_decoder.eval(f"self._read_rlp_number({two_byte_number}, 0)")
    assert value == 256, "Should decode two-byte number correctly"
    assert next_pos == 3, "Should advance position by 3"


def test_read_hash32(block_headers_decoder):
    """
    Test _read_hash32 function
    """
    # Create a sample hash (32 bytes) with a 0xa0 prefix
    hash_bytes = bytes([0xA0]) + bytes(range(32))  # 0xa0 + 32 bytes of incrementing values

    hash_value, next_pos = block_headers_decoder.eval(f"self._read_hash32({hash_bytes}, 0)")

    # Extract expected hash (without the 0xa0 prefix)
    expected_hash = bytes(range(32))
    expected_hash_padded = expected_hash.ljust(32, b"\0")  # Ensure it's exactly 32 bytes

    # Convert to hex strings for better error reporting
    hash_hex = "0x" + binascii.hexlify(hash_value).decode()
    expected_hex = "0x" + binascii.hexlify(expected_hash_padded).decode()

    assert (
        hash_value == expected_hash_padded
    ), f"Hash mismatch: got {hash_hex}, expected {expected_hex}"
    assert next_pos == 33, "Should advance position by 33 (1 for prefix + 32 for hash)"
