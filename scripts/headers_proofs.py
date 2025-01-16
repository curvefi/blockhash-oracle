from web3 import Web3
import rlp
import os


# create a proof given block dict
def create_proof(block_data):
    fields = [
        block_data["parentHash"],  # 1. parentHash
        block_data["sha3Uncles"],  # 2. uncleHash
        bytes.fromhex(block_data["miner"][2:]),  # 3. coinbase (returned as string!)
        block_data["stateRoot"],  # 4. root
        block_data["transactionsRoot"],  # 5. txHash
        block_data["receiptsRoot"],  # 6. receiptHash
        block_data["logsBloom"],  # 7. logsBloom
        block_data["difficulty"],  # 8. difficulty (big.Int)
        block_data["number"],  # 9. number (big.Int)
        block_data["gasLimit"],  # 10. gasLimit
        block_data["gasUsed"],  # 11. gasUsed
        block_data["timestamp"],  # 12. timestamp
        block_data["extraData"],  # 13. extraData
        block_data["mixHash"],  # 14. mixHash
        block_data["nonce"],  # 15. nonce (8 bytes)
    ]

    # Optionally append newer EIP fields only if they exist
    if block_data.get("baseFeePerGas") is not None:
        fields.append(block_data["baseFeePerGas"])
    if block_data.get("withdrawalsRoot") not in [None, "0x"]:
        fields.append(block_data["withdrawalsRoot"])
    if block_data.get("blobGasUsed") is not None:
        fields.append(block_data["blobGasUsed"])
    if block_data.get("excessBlobGas") is not None:
        fields.append(block_data["excessBlobGas"])
    if block_data.get("parentBeaconBlockRoot") not in [None, "0x"]:
        fields.append(block_data["parentBeaconBlockRoot"])
    if block_data.get("requestsHash") not in [None, "0x"]:
        fields.append(block_data["requestsHash"])

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
