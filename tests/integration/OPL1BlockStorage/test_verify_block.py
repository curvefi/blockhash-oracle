import boa
import pytest
from web3 import Web3
import rlp
from hexbytes import HexBytes
import os


# Convert various data types (HexBytes, "0x..." string, or int) into raw bytes.
def to_bytes(value):
    if isinstance(value, HexBytes):
        return bytes(value)
    elif isinstance(value, str) and value.startswith("0x"):
        return bytes.fromhex(value[2:])
    elif isinstance(value, (bytes, bytearray)):
        return value
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
    return encoded_header, calculated_hash


@pytest.mark.base
def test_prove_block(forked_env, op_l1_storage, rpc_url):
    # get latest known block
    latest_block = op_l1_storage.last_fetched_block()
    # make sure previous one is unknown
    assert not op_l1_storage.is_fetched(latest_block - 1)
    # print(f"Latest block: {latest_block}")

    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(rpc_url.replace("base", "ethereum")))
    # Fetch a block and build proof
    block = w3.eth.get_block(latest_block)
    encoded_header, calculated_hash = create_proof(block)

    assert calculated_hash == block["hash"]  # check that our rlp corresponds to onchain logic
    assert to_bytes(calculated_hash) == op_l1_storage.get_block_hash(
        latest_block
    )  # double check with our storage

    # call the verify function to insert prev_block
    op_l1_storage.verify_preceeding_block(latest_block, encoded_header)

    # Fetch newly added previous block
    prev_hash, prev_ts = op_l1_storage.l1_blocks(latest_block - 1)
    assert prev_hash == block["parentHash"]
    print(f"Previous block hash: {prev_hash.hex()}")
    print(f"Previous block timestamp: {prev_ts}")


@pytest.mark.base
def test_prove_many_blocks(forked_env, op_l1_storage, rpc_url):
    # get latest known block
    latest_block = op_l1_storage.last_fetched_block()
    # print(f"Latest block: {latest_block}")
    n_prove = 10
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(rpc_url.replace("base", "ethereum")))
    for block_n in range(latest_block, latest_block - n_prove, -1):
        # make sure previous block is unknown
        assert not op_l1_storage.is_fetched(block_n - 1)

        # Fetch a block and build proof
        block = w3.eth.get_block(block_n)
        encoded_header, calculated_hash = create_proof(block)

        assert calculated_hash == block["hash"]  # check that our rlp corresponds to onchain logic
        assert to_bytes(calculated_hash) == op_l1_storage.get_block_hash(
            block_n
        )  # double check with our storage

        # call the verify function to insert prev_block
        op_l1_storage.verify_preceeding_block(block_n, encoded_header)

        # Fetch newly added previous block
        prev_hash, prev_ts = op_l1_storage.l1_blocks(block_n - 1)
        assert prev_hash == block["parentHash"]
        print(f"Previous block hash: {prev_hash.hex()}")
        print(f"Previous block timestamp: {prev_ts}")
