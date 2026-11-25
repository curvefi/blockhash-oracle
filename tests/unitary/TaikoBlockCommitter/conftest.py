import boa
import pytest

MOCKS = "tests/unitary/TaikoBlockCommitter/mocks/"


@pytest.fixture()
def signal_service():
    return boa.load(MOCKS + "MockSignalService.vy")


@pytest.fixture()
def anchor():
    return boa.load(MOCKS + "MockAnchor.vy")


@pytest.fixture()
def committer(block_oracle, signal_service, anchor, dev_deployer):
    """TaikoBlockCommitter as the oracle's only committer"""
    with boa.env.prank(dev_deployer):
        committer = boa.load(
            "contracts/native/TaikoBlockCommitter.vy",
            block_oracle.address,
            signal_service.address,
            anchor.address,
        )
        block_oracle.add_committer(committer.address, True)
    return committer
