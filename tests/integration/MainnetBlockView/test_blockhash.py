import pytest
import boa

pytestmark = pytest.mark.mainnet


@pytest.fixture(autouse=True)
def setup(forked_env):
    pass


@pytest.mark.mainnet
def test_default_behavior(mainnet_block_view, eth_web3_client):
    block = boa.env.evm.patch.block_number
    block_number, block_hash = mainnet_block_view.get_blockhash()

    assert block_number == block - 65, "Default block number incorrect"
    # not validating hashes because boa can't
    # web3_reference = eth_web3_client.eth.get_block(block - 65)["hash"]
    # assert block_hash == web3_reference, "Block hash mismatch"


@pytest.mark.mainnet
def test_specific_block(mainnet_block_view, eth_web3_client):
    block = boa.env.evm.patch.block_number
    test_block = block - 100

    block_number, block_hash = mainnet_block_view.get_blockhash(test_block)
    assert block_number == test_block, "Returned block number mismatch"
    # not validating hashes because boa can't
    # web3_reference = eth_web3_client.eth.get_block(test_block)["hash"]
    # assert block_hash == web3_reference, "Block hash mismatch"


@pytest.mark.mainnet
def test_out_of_range_failures(mainnet_block_view):
    current_block = boa.env.evm.patch.block_number

    # Too recent
    with boa.reverts():
        mainnet_block_view.get_blockhash(current_block - 64, False)

    # Too old
    with boa.reverts():
        mainnet_block_view.get_blockhash(current_block - 257, False)


@pytest.mark.mainnet
def test_out_of_range_safe(mainnet_block_view):
    current_block = boa.env.evm.patch.block_number

    # Too recent
    assert mainnet_block_view.get_blockhash(current_block - 64, True) == (0, b"\x00" * 32)

    # Too old
    assert mainnet_block_view.get_blockhash(current_block - 8_192 - 1, True) == (0, b"\x00" * 32)
