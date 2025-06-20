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
def test_out_of_range_safe(mainnet_block_view):
    current_block = boa.env.evm.patch.block_number

    # Too recent
    assert mainnet_block_view.get_blockhash(current_block - 64, True) == (0, b"\x00" * 32)

    # Too old
    assert mainnet_block_view.get_blockhash(current_block - 8_192 - 1, True) == (0, b"\x00" * 32)


@pytest.mark.mainnet
@pytest.mark.parametrize("delta", [8193, 8192, 8191, 257, 256, 255, 128, 64])
def test_particular_cases(mainnet_block_view, delta):
    current_block = boa.env.evm.patch.block_number
    query_block = current_block - delta
    if delta == 256:
        try:
            # boa failure here
            mainnet_block_view.get_blockhash(query_block, True)
        except Exception as e:
            print(e)
    else:
        number, hash = mainnet_block_view.get_blockhash(query_block, True)
        if delta < 8192 and delta > 64:
            assert number != 0, "Return must be nonzero"
        else:
            assert number == 0, "Return must be zero"


@pytest.mark.mainnet
def test_raise_on_failure(mainnet_block_view):
    current_block = boa.env.evm.patch.block_number
    with boa.reverts():
        mainnet_block_view.get_blockhash(current_block - 1, False)

    with boa.reverts():
        mainnet_block_view.get_blockhash(current_block - 8192 - 1, False)

    with boa.reverts():
        mainnet_block_view.get_blockhash(current_block - 64, False)

    with boa.reverts():
        mainnet_block_view.get_blockhash(current_block - 8192, False)
