import os
import re
from pathlib import Path

import boa
import pytest

# Real deployed contract on Ethereum mainnet; typeAndVersion() reads "WorkflowRegistry 2.0.0"
WORKFLOW_REGISTRY = "0x4Ac54353FA4Fa961AfcC5ec4B118596d3305E7e5"

# Real DON families on the mainnet registry, from getDonConfigs
DON_FAMILY = "zone-a"
OTHER_DON_FAMILY = "zone-b"

STATUS_ACTIVE = 0
STATUS_PAUSED = 1

WORKFLOW_NAME = "curve-blockhash-fork-test"
TAG = "v1"
BINARY_URL = "https://artifacts.example/blockhash-relay/binary.wasm.br.b64"
CONFIG_URL = "https://artifacts.example/blockhash-relay/config.json"
NEW_CONFIG_URL = "https://artifacts.example/blockhash-relay/config-two-hubs.json"

# Only what these tests call. The registry's own ABI, transcribed from the v2 Go binding
REGISTRY_ABI = """[
 {"type":"function","name":"typeAndVersion","stateMutability":"view","inputs":[],
  "outputs":[{"name":"","type":"string"}]},
 {"type":"function","name":"getConfig","stateMutability":"view","inputs":[],
  "outputs":[{"name":"maxNameLen","type":"uint8"},{"name":"maxTagLen","type":"uint8"},
             {"name":"maxUrlLen","type":"uint8"},{"name":"maxAttrLen","type":"uint16"},
             {"name":"maxExpiryLen","type":"uint32"}]},
 {"type":"function","name":"getLinkedOwners","stateMutability":"view",
  "inputs":[{"name":"start","type":"uint256"},{"name":"batchSize","type":"uint256"}],
  "outputs":[{"name":"","type":"address[]"}]},
 {"type":"function","name":"totalActiveWorkflowsByOwner","stateMutability":"view",
  "inputs":[{"name":"owner","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
 {"type":"function","name":"getMaxWorkflowsPerUserDON","stateMutability":"view",
  "inputs":[{"name":"user","type":"address"},{"name":"donFamily","type":"string"}],
  "outputs":[{"name":"","type":"uint32"}]},
 {"type":"function","name":"getWorkflow","stateMutability":"view",
  "inputs":[{"name":"owner","type":"address"},{"name":"workflowName","type":"string"},
            {"name":"tag","type":"string"}],
  "outputs":[{"name":"","type":"tuple","components":[
      {"name":"workflowId","type":"bytes32"},{"name":"owner","type":"address"},
      {"name":"createdAt","type":"uint64"},{"name":"status","type":"uint8"},
      {"name":"workflowName","type":"string"},{"name":"binaryUrl","type":"string"},
      {"name":"configUrl","type":"string"},{"name":"tag","type":"string"},
      {"name":"attributes","type":"bytes"},{"name":"donFamily","type":"string"}]}]},
 {"type":"function","name":"upsertWorkflow","stateMutability":"nonpayable","outputs":[],
  "inputs":[{"name":"workflowName","type":"string"},{"name":"tag","type":"string"},
            {"name":"workflowId","type":"bytes32"},{"name":"status","type":"uint8"},
            {"name":"donFamily","type":"string"},{"name":"binaryUrl","type":"string"},
            {"name":"configUrl","type":"string"},{"name":"attributes","type":"bytes"},
            {"name":"keepAlive","type":"bool"}]},
 {"type":"function","name":"pauseWorkflow","stateMutability":"nonpayable","outputs":[],
  "inputs":[{"name":"workflowId","type":"bytes32"}]},
 {"type":"function","name":"deleteWorkflow","stateMutability":"nonpayable","outputs":[],
  "inputs":[{"name":"workflowId","type":"bytes32"}]}
]"""


@pytest.fixture(scope="session")
def rpc_url(drpc_api_key):
    """Override the parent conftest: always fork Ethereum mainnet, where the registry lives."""
    override = os.getenv("MAINNET_FORK_RPC")
    if override:
        return override
    return f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"


@pytest.fixture()
def registry(forked_env):
    return boa.loads_abi(REGISTRY_ABI, name="WorkflowRegistry").at(WORKFLOW_REGISTRY)


@pytest.fixture()
def linked_owner(registry):
    """A real address already linked in the registry, with room in its DON quota."""
    for owner in registry.getLinkedOwners(0, 40):
        if registry.totalActiveWorkflowsByOwner(owner) == 0:
            boa.env.set_balance(owner, 10**19)
            return owner
    pytest.skip("no linked owner with a free workflow slot in the first 40")


def proxy_bounds():
    """The proxy's String/Bytes bounds, read out of its source."""
    source = Path("contracts/CREWorkflowProxy.vy").read_text(encoding="utf-8")
    return {
        name: int(value)
        for name, value in re.findall(r"^(MAX_\w+): constant\(uint256\) = (\d+)$", source, re.M)
    }


def wid(seed: int) -> bytes:
    """A workflow id shaped like a real one: 32 bytes with the version byte zeroed."""
    return b"\x00" + seed.to_bytes(31, "big")
