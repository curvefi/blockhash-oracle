from web3 import Web3
import rlp
from hexbytes import HexBytes
import os


# Convert various data types (HexBytes, "0x..." string, or int) into raw bytes.
def to_bytes(value):
    if isinstance(value, (bytes, bytearray)):
        return value
    if isinstance(value, HexBytes):
        return bytes(value)
    if isinstance(value, str) and value.startswith("0x"):
        return bytes.fromhex(value[2:])
    raise TypeError(f"Cannot convert {value!r} to bytes.")


# Convert a value (possibly "0x..." or int) into an integer.
def to_int(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    raise ValueError(f"Cannot convert {value} to int.")


# create a proof given block dict
def create_proof(block):
    fields = [
        to_bytes(block["parentHash"]),  # 1. parentHash
        to_bytes(block["sha3Uncles"]),  # 2. uncleHash
        to_bytes(block["miner"]),  # 3. coinbase
        to_bytes(block["stateRoot"]),  # 4. root
        to_bytes(block["transactionsRoot"]),  # 5. txHash
        to_bytes(block["receiptsRoot"]),  # 6. receiptHash
        to_bytes(block["logsBloom"]),  # 7. logsBloom
        to_int(block["difficulty"]),  # 8. difficulty (big.Int)
        to_int(block["number"]),  # 9. number (big.Int)
        block["gasLimit"],  # 10. gasLimit
        block["gasUsed"],  # 11. gasUsed
        block["timestamp"],  # 12. timestamp
        to_bytes(block["extraData"]),  # 13. extraData
        to_bytes(block["mixHash"]),  # 14. mixHash
        to_bytes(block["nonce"]),  # 15. nonce (8 bytes)
    ]

    # Optionally append newer EIP fields only if they exist (EIP-1559, 4895, etc.)
    if block.get("baseFeePerGas") is not None:
        fields.append(to_int(block["baseFeePerGas"]))
    if block.get("withdrawalsRoot") not in [None, "0x"]:
        fields.append(to_bytes(block["withdrawalsRoot"]))
    if block.get("blobGasUsed") is not None:
        fields.append(block["blobGasUsed"])
    if block.get("excessBlobGas") is not None:
        fields.append(block["excessBlobGas"])
    if block.get("parentBeaconBlockRoot") not in [None, "0x"]:
        fields.append(to_bytes(block["parentBeaconBlockRoot"]))
    if block.get("requestsHash") not in [None, "0x"]:
        fields.append(to_bytes(block["requestsHash"]))

    # RLP-encode header and compute keccak256
    encoded_header = rlp.encode(fields)
    calculated_hash = Web3.keccak(encoded_header)
    return encoded_header, calculated_hash, fields


# Initialize Web3
w3 = Web3(
    Web3.HTTPProvider(
        "https://lb.drpc.org/ogrpc?network=ethereum&dkey=" + os.getenv("DRPC_API_KEY")
    )
)

# Fetch a block
block_num = 21579069
for i in range(block_num - 1, block_num):
    block = w3.eth.get_block(block_num)
    encoded_header, calculated_hash, fields = create_proof(block)

    print(block["number"], len(fields), len(encoded_header))

    # print(block["parentHash"].hex())
    # print(encoded_header.hex())
    # Find substring
    start_nibble = encoded_header.hex().find(block["parentHash"].hex())
    if start_nibble == -1:
        print("Parent hash was not found in the RLP hex.")
    else:
        end_nibble = start_nibble + len(block["parentHash"].hex())
        start_byte = start_nibble // 2
        end_byte = end_nibble // 2

    print(f"Parent hash found in RLP hex at nibble-offset {start_nibble} to {end_nibble}.")
    print(f"Which is byte-offset {start_byte} to {end_byte} in the RLP data.")
    print("Calculated RLP-hash  :", calculated_hash.hex())
    print("Official block hash  :", block["hash"].hex())

    if calculated_hash == block["hash"]:
        print("Success! They match.")
    else:
        print("Mismatch - check field ordering or data conversions.")
