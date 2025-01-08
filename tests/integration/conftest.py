import boa
import pytest
import os
import json

boa.set_etherscan(api_key=os.getenv("ETHERSCAN_API_KEY"))
BOA_CACHE = False

ALL_CHAINS = []
OP_CHAINS = []
NON_OP_CHAINS = []
with open("chains.json", "r") as file:
    chains = json.load(file)
    ALL_CHAINS = chains.keys()
    for chain in chains:
        if len(chains[chain]["l1block"]) == 42:
            OP_CHAINS.append(chain)
        else:
            NON_OP_CHAINS.append(chain)


@pytest.fixture(scope="session")
def chains():
    with open("chains.json", "r") as file:
        return json.load(file)


@pytest.fixture(scope="session")
def drpc_api_key():
    return os.getenv("DRPC_API_KEY")


# Collect chain names dynamically for parameterization
def pytest_generate_tests(metafunc):
    """Dynamically add chain names as test parameters."""
    # Run all tests on all chains by default
    if "chain_name" in metafunc.fixturenames:
        selected_chains = set()

        # Check all marks applied to the test and filter chains
        for marker in metafunc.definition.own_markers:
            if marker.name in ALL_CHAINS:  # Match the chain names from chains.json
                selected_chains.add(marker.name)
            elif marker.name == "op_chains":
                selected_chains.update(OP_CHAINS)
            elif marker.name == "non_op_chains":
                selected_chains.update(NON_OP_CHAINS)

        # If no marks are applied, run on all chains
        if not selected_chains:
            selected_chains.update(ALL_CHAINS)

        metafunc.parametrize("chain_name", selected_chains)


@pytest.fixture(scope="function")
def rpc_url(chains, chain_name, drpc_api_key):
    """Fixture to generate the correct RPC URL for each chain."""
    chain = chains[chain_name]
    # Use public RPC if no DRPC key provided
    return chain["drpc"] + drpc_api_key if drpc_api_key else chain["rpc"]


@pytest.fixture()
def forked_env(rpc_url):
    """Automatically fork each test with the specified chain."""
    block_to_fork = "latest"
    with boa.swap_env(boa.Env()):
        if BOA_CACHE:
            boa.fork(url=rpc_url, block_identifier=block_to_fork)
        else:
            boa.fork(url=rpc_url, block_identifier=block_to_fork, cache_file=None)
        boa.env.enable_fast_mode()
        yield


@pytest.fixture()
def oracle():
    _oracle = boa.load("contracts/BlockhashOracle.vy")
    return _oracle


@pytest.fixture()
def op_l1_storage(chains, chain_name):
    L1Block_address = chains[chain_name]["l1block"]
    if not L1Block_address:
        pytest.skip("No L1Block contract address found for this chain.")
    _op_l1_storage = boa.load("contracts/OPL1BlockStorage.vy", L1Block_address)
    return _op_l1_storage
