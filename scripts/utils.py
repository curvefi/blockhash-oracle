from rlp import encode


def encode_headers(block_data):
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

    return encode(fields)
