from web3 import Web3
import os
from headers_proofs import create_proof
import rlp

# Initialize Web3
w3 = Web3(
    Web3.HTTPProvider(
        "https://lb.drpc.org/ogrpc?network=ethereum&dkey=" + os.getenv("DRPC_API_KEY")
    )
)

# Fetch a block
block_num = 21579069
blocks_list = []
for i in range(block_num - 10, block_num, 1):
    block = w3.eth.get_block(i)
    encoded_header, calculated_hash, fields = create_proof(block)
    print(block["number"], len(fields), len(encoded_header))
    blocks_list.append(encoded_header)

encoded_array = rlp.encode(blocks_list)
print(len(encoded_array))
