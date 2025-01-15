from web3 import Web3
import os
from headers_proofs import create_proof


def rlp_decode_item(data: bytes, pos: int = 0):
    """
    Decodes a single RLP item (string or list) starting at `pos` in `data`.
    Returns a tuple: (python_value, new_pos).

    python_value can be either `bytes` (for an RLP "string") or `list` (for an RLP "list").
    new_pos is the index in `data` after reading this item.
    """
    if pos >= len(data):
        raise ValueError("No more data to decode.")

    prefix = data[pos]
    # 1) Single byte 0x00..0x7f => itself
    if prefix <= 0x7F:
        return (data[pos : pos + 1], pos + 1)

    # 2) 0x80..0xb7 => short string
    elif prefix <= 0xB7:
        str_len = prefix - 0x80
        start = pos + 1
        end = start + str_len
        if end > len(data):
            raise ValueError("RLP string exceeds data length.")
        return (data[start:end], end)

    # 3) 0xb8..0xbf => long string
    elif prefix <= 0xBF:
        len_of_str_len = prefix - 0xB7
        start_len = pos + 1
        end_len = start_len + len_of_str_len
        if end_len > len(data):
            raise ValueError("Not enough bytes to read length of string.")
        str_len = int.from_bytes(data[start_len:end_len], "big")
        start_str = end_len
        end_str = start_str + str_len
        if end_str > len(data):
            raise ValueError("RLP string exceeds data length.")
        return (data[start_str:end_str], end_str)

    # 4) 0xc0..0xf7 => short list
    elif prefix <= 0xF7:
        list_len = prefix - 0xC0
        start = pos + 1
        end = start + list_len
        if end > len(data):
            raise ValueError("RLP list exceeds data length.")

        items = []
        cur = start
        while cur < end:
            (item, new_pos) = rlp_decode_item(data, cur)
            items.append(item)
            cur = new_pos
        if cur != end:
            raise ValueError("Decoded list length does not match prefix length.")
        return (items, end)

    # 5) 0xf8..0xff => long list
    else:
        len_of_list_len = prefix - 0xF7
        start_len = pos + 1
        end_len = start_len + len_of_list_len
        if end_len > len(data):
            raise ValueError("Not enough bytes to read length of list.")
        list_len = int.from_bytes(data[start_len:end_len], "big")
        start_list = end_len
        end_list = start_list + list_len
        if end_list > len(data):
            raise ValueError("RLP list exceeds data length.")

        items = []
        cur = start_list
        while cur < end_list:
            (item, new_pos) = rlp_decode_item(data, cur)
            items.append(item)
            cur = new_pos
        if cur != end_list:
            raise ValueError("Decoded list length does not match prefix length.")
        return (items, end_list)


def rlp_decode(data: bytes):
    """
    Convenience function to decode the entire RLP data,
    expecting one top-level item (which could be a list).
    """
    (value, pos_after) = rlp_decode_item(data, 0)
    # If there's trailing data, either ignore or treat as an error:
    if pos_after != len(data):
        raise ValueError("Extra unconsumed bytes after top-level item.")
    return value


# Initialize Web3
w3 = Web3(
    Web3.HTTPProvider(
        "https://lb.drpc.org/ogrpc?network=ethereum&dkey=" + os.getenv("DRPC_API_KEY")
    )
)

# Fetch a block
block_num = 21579069
block = w3.eth.get_block(block_num)
encoded_header, calculated_hash, fields = create_proof(block)
print(encoded_header.hex())
print(block["number"], len(encoded_header))

# Decode the RLP-encoded header
decoded_header = rlp_decode(encoded_header)
assert len(fields) == len(decoded_header)
for i in range(len(fields)):
    print("Field", i)
    try:
        print(fields[i].hex(), decoded_header[i].hex())
    except:
        print(fields[i], decoded_header[i])

    if fields[i] != decoded_header[i]:
        print("Mismatch at index", i)
        # break
    else:
        print("Match at index", i)
