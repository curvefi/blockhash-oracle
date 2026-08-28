import hashlib

import boa
import pytest

EMPTY_ADDRESS = boa.eval("empty(address)")
EMPTY_BYTES32 = boa.eval("empty(bytes32)")

MOCKS = "tests/unitary/CREWorkflowProxy/mocks"

WORKFLOW_NAME = "blockhash-relay"
DON_FAMILY = "test-don-family"
TAG = "v1"

BINARY_URL = "https://artifacts.example/blockhash-relay/binary.wasm.br.b64"
CONFIG_URL = "https://artifacts.example/blockhash-relay/config.json"
NEW_CONFIG_URL = "https://artifacts.example/blockhash-relay/config-two-hubs.json"
ROGUE_BINARY_URL = "https://rogue.example/binary.wasm.br.b64"

STATUS_ACTIVE = 0

WASM = b"\x00asm\x01\x00\x00\x00 approved by the DAO"
ROGUE_WASM = b"\x00asm\x01\x00\x00\x00 not approved by anyone"
CONFIG = b'{"requestHubs":[]}'
NEW_CONFIG = b'{"requestHubs":[{"chainSelectorName":"ethereum-testnet-sepolia-base-1"}]}'


def workflow_id(owner, name, wasm, config, secrets_url=""):
    """chainlink-common GenerateWorkflowID: sha256 over the artifacts, first byte zeroed."""
    digest = hashlib.sha256()
    digest.update(bytes.fromhex(owner.removeprefix("0x")))
    digest.update(name.encode())
    digest.update(wasm)
    digest.update(config)
    digest.update(secrets_url.encode())
    return b"\x00" + digest.digest()[1:]


@pytest.fixture()
def ownership_admin():
    return boa.env.generate_address()


@pytest.fixture()
def parameter_admin():
    return boa.env.generate_address()


@pytest.fixture()
def emergency_admin():
    return boa.env.generate_address()


@pytest.fixture()
def alice():
    return boa.env.generate_address()


@pytest.fixture(scope="session")
def proxy_deployer():
    return boa.load_partial("contracts/CREWorkflowProxy.vy")


@pytest.fixture(scope="session")
def mock_registry_deployer():
    return boa.load_partial(f"{MOCKS}/MockWorkflowRegistry.vy")


@pytest.fixture()
def registry(dev_deployer, mock_registry_deployer):
    with boa.env.prank(dev_deployer):
        return mock_registry_deployer.deploy()


@pytest.fixture()
def proxy(
    dev_deployer, registry, ownership_admin, parameter_admin, emergency_admin, proxy_deployer
):
    with boa.env.prank(dev_deployer):
        return proxy_deployer.deploy(
            registry.address,
            WORKFLOW_NAME,
            DON_FAMILY,
            ownership_admin,
            parameter_admin,
            emergency_admin,
        )


@pytest.fixture()
def approved(proxy, ownership_admin):
    """Proxy with a binary approved, the state every config update starts from."""
    with boa.env.prank(ownership_admin):
        proxy.approve_binary(TAG, approved_id(proxy), BINARY_URL, CONFIG_URL, b"", False)
    return proxy


def approved_id(proxy):
    """The id of the (approved binary, initial config) pair the `approved` fixture registers."""
    return workflow_id(proxy.address, WORKFLOW_NAME, WASM, CONFIG)
