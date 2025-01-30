import boa
import pytest
import os
from web3 import Web3
from rlp import encode
import pickle

boa.set_etherscan(api_key=os.getenv("ETHERSCAN_API_KEY"))


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


@pytest.fixture(scope="session")
def drpc_api_key():
    api_key = os.getenv("DRPC_API_KEY")
    assert api_key is not None, "DRPC_API_KEY environment variable not set"
    return api_key


@pytest.fixture(scope="session")
def eth_web3_client(drpc_api_key):
    if drpc_api_key:
        rpc_url = f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"
    else:
        rpc_url = "https://rpc.ankr.com/eth"
    return Web3(Web3.HTTPProvider(rpc_url))


@pytest.fixture(scope="session")
def block_number(request):
    if hasattr(request, "param"):
        return request.param
    else:
        return 21579069


@pytest.fixture(scope="session")
def blocks_cache_file():
    return "blocks.pklcache"


@pytest.fixture(scope="session")
def block_data(eth_web3_client, block_number):
    """Fetch a real block from mainnet"""
    block = eth_web3_client.eth.get_block(block_number, full_transactions=False)
    return block


@pytest.fixture(scope="session")
def n_blocks_data(eth_web3_client, block_number, request, blocks_cache_file):
    """Fetch a real block from mainnet"""
    n_blocks = request.param
    res = []
    should_save = False
    # Check if cache exists
    if os.path.exists(blocks_cache_file):
        with open(blocks_cache_file, "rb") as f:
            cache_dict = pickle.load(f)
            print("Blocks cache loaded from file")
    else:
        cache_dict = {}
    if block_number == "latest":
        block_number = eth_web3_client.eth.block_number
    for i in range(block_number, block_number - n_blocks, -1):
        if i in cache_dict:
            block = cache_dict[i]
        else:
            block = eth_web3_client.eth.get_block(i, full_transactions=False)
            cache_dict[i] = block
            should_save = True
            print(f"Block {i} fetched from RPC")
        res.append(block)
    if should_save:
        with open(blocks_cache_file, "wb") as f:
            pickle.dump(cache_dict, f)
            print("Blocks cache saved to file")
    return res


@pytest.fixture(scope="session")
def n_encoded_blocks_headers(n_blocks_data):
    """Encode block header fields in RLP format"""
    # print(block_data)  # debug line
    return [encode_headers(block_data) for block_data in n_blocks_data]


@pytest.fixture(scope="session")
def encoded_block_header(block_data):
    """Encode block header fields in RLP format"""
    # print(block_data)  # debug line
    return encode_headers(block_data)


@pytest.fixture()
def dev_deployer():
    return boa.env.generate_address()


@pytest.fixture()
def block_oracle(dev_deployer):
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/BlockOracle.vy")


@pytest.fixture()
def mainnet_block_view(dev_deployer):
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/MainnetBlockView.vy")
