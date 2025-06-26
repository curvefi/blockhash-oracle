from rlp import encode


def ensure_bytes(input_value):
    # Already bytes, return as-is
    if isinstance(input_value, bytes):
        return input_value

    # Handle hex strings (e.g., "0x1234" or "1234")
    if isinstance(input_value, str):
        # Strip "0x" prefix if present, otherwise assume raw hex
        hex_str = input_value[2:] if input_value.startswith("0x") else input_value
        return bytes.fromhex(hex_str)


def encode_headers(block_data):
    fields = [
        block_data["parentHash"],  # 1. parentHash!
        block_data["sha3Uncles"],  # 2. uncleHash
        ensure_bytes(block_data["miner"]),  # 3. coinbase (returned as string!)
        block_data["stateRoot"],  # 4. root
        block_data["transactionsRoot"],  # 5. txHash
        block_data["receiptsRoot"],  # 6. receiptHash
        block_data["logsBloom"],  # 7. logsBloom
        block_data["difficulty"],  # 8. difficulty (big.Int)
        block_data["number"],  # 9. number (big.Int)
        block_data["gasLimit"],  # 10. gasLimit
        block_data["gasUsed"],  # 11. gasUsed
        block_data["timestamp"],  # 12. timestamp
        block_data.get(
            "extraData", block_data.get("proofOfAuthorityData")
        ),  # 13. extraData or proofOfAuthorityData
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
        fields.append(ensure_bytes(block_data["requestsHash"]))

    for i, f in enumerate(fields):
        print(f"Field {i}: {f}")

    return encode(fields)
