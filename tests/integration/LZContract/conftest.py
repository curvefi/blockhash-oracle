import pytest
import boa
import os

LZ_ENDPOINT_BASE_SEPOLIA = "0x6EDCE65403992e310A62460808c4b910D972f10f"
LZ_CHAIN_ID = 84532
LZ_ENDPOINT_ID = 40245


@pytest.fixture(scope="session")
def rpc_url():
    return "https://sepolia.base.org"


@pytest.fixture(scope="session")
def scan_api():
    return os.getenv("BASESCAN_API_KEY")


@pytest.fixture(scope="session")
def scan_url():
    return "https://api-sepolia.basescan.org/api"


@pytest.fixture()
def lz_contract(dev_deployer):
    with boa.env.prank(dev_deployer):
        return boa.load("contracts/LZContract.vy", LZ_ENDPOINT_BASE_SEPOLIA)
