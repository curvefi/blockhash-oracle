import pytest
from web3 import Web3
import boa


# # Helper function to connect and verify chain ID
# def verify_chain_id(rpc_url, expected_chain_id):
#     w3 = Web3(Web3.HTTPProvider(rpc_url))
#     assert w3.is_connected(), f"Failed to connect to {rpc_url}"
#     chain_id = w3.eth.chain_id
#     assert (
#         chain_id == expected_chain_id
#     ), f"Chain ID mismatch for {rpc_url}. Expected {expected_chain_id}, got {chain_id}"


# # Test to verify all chains using both public RPC and DRPC (with API key)
# def test_chain_connections(chains, chain_name, drpc_api_key):
#     chain = chains[chain_name]
#     expected_chain_id = chain["id"]

#     # Test public RPC connection
#     verify_chain_id(chain["rpc"], expected_chain_id)

#     # # Test DRPC connection (with API key)
#     drpc_url = f"{chain['drpc']}{drpc_api_key}"
#     verify_chain_id(drpc_url, expected_chain_id)


def test_forked_env(forked_env, chain_name):
    """Test interacting with a forked environment for each chain."""
    print(
        f"Running test on {chain_name} in fork mode! Latest block: {boa.env.evm.patch.block_number} and chain ID: {boa.env.evm.patch.chain_id}"
    )
