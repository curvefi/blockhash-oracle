import boa
import pytest

EMPTY_ADDRESS = boa.eval("empty(address)")
EMPTY_BYTES32 = boa.eval("empty(bytes32)")

MOCKS = "tests/unitary/BlockhashRequestHub/mocks"

# Real identifiers, per the project convention of not inventing chain ids
BASE_EID = 30184
ARBITRUM_EID = 30110
KAVA_EID = 30177  # LayerZero only, no CCIP lane

BASE_CHAIN_SELECTOR = 15971525489660198786
ARBITRUM_CHAIN_SELECTOR = 4949039107694359620

LZ_ONE = [BASE_EID]
LZ_TWO = [BASE_EID, ARBITRUM_EID]
CCIP_ONE = [BASE_CHAIN_SELECTOR]
CCIP_TWO = [BASE_CHAIN_SELECTOR, ARBITRUM_CHAIN_SELECTOR]

RAIL_LZ = 1
RAIL_CRE = 2
RAIL_BOTH = RAIL_LZ | RAIL_CRE

# Mock relay pricing
READ_FEE = 10**16
LZ_BROADCAST_FEE = 10**15
CCIP_FEE = 2 * 10**15

# Hub configuration
BASE_FEE = 10**15
FEE_PER_TARGET = 5 * 10**14
FEE_MULTIPLIER_BPS = 25_000  # 250%, generous headroom by design
BASE_ON_REPORT_GAS = 300_000
CCIP_SEND_GAS = 150_000

CCIP_RECEIVE_GAS_LIMIT = 150_000
LZ_RECEIVE_GAS_LIMIT = 150_000
LZ_READ_GAS_LIMIT = 300_000

# Any block above the oracle's height; the oracle starts empty in these tests
PINNED_BLOCK = 21_000_000
BLOCK_HASH = boa.eval("keccak256(b'block')")


def ccip_max_fee(n_targets=1):
    """What the hub caps each CCIP send at, given the mock's flat quote."""
    return CCIP_FEE * FEE_MULTIPLIER_BPS // 10_000 * n_targets


def surcharge(n_targets):
    return BASE_FEE + n_targets * FEE_PER_TARGET


def cre_cost(n_targets):
    return ccip_max_fee(n_targets) + surcharge(n_targets)


def lz_cost(n_targets):
    """quote_read_fee folds the broadcast value into the read quote."""
    return READ_FEE + LZ_BROADCAST_FEE * n_targets


def cre_vote(block_oracle, relay, block_number=PINNED_BLOCK, block_hash=BLOCK_HASH):
    """Cast the CRE relay's vote, the way a real onReport would."""
    with boa.env.prank(relay.address):
        block_oracle.commit_block(block_number, block_hash)


@pytest.fixture()
def alice():
    addr = boa.env.generate_address()
    boa.env.set_balance(addr, 10**20)
    return addr


# Compile once per session; importing the real relays for their interfaces makes compiling the hub
# expensive, and boa.load per test costs minutes across the suite.
@pytest.fixture(scope="session")
def hub_deployer():
    return boa.load_partial("contracts/BlockhashRequestHub.vy")


@pytest.fixture(scope="session")
def mock_lz_deployer():
    return boa.load_partial(f"{MOCKS}/MockLZBlockRelay.vy")


@pytest.fixture(scope="session")
def mock_cre_deployer():
    return boa.load_partial(f"{MOCKS}/MockChainlinkBlockRelay.vy")


@pytest.fixture()
def mock_lz_relay(dev_deployer, block_oracle, mock_lz_deployer):
    with boa.env.prank(dev_deployer):
        relay = mock_lz_deployer.deploy(block_oracle.address, READ_FEE, LZ_BROADCAST_FEE)
        relay.set_peer(BASE_EID, boa.eval("convert(1, bytes32)"))
        relay.set_peer(ARBITRUM_EID, boa.eval("convert(2, bytes32)"))
        relay.set_peer(KAVA_EID, boa.eval("convert(3, bytes32)"))
    return relay


@pytest.fixture()
def mock_cre_relay(dev_deployer, block_oracle, mock_cre_deployer):
    with boa.env.prank(dev_deployer):
        relay = mock_cre_deployer.deploy(block_oracle.address, CCIP_FEE)
        relay.set_receiver(BASE_CHAIN_SELECTOR, boa.env.generate_address())
        relay.set_receiver(ARBITRUM_CHAIN_SELECTOR, boa.env.generate_address())
    return relay


@pytest.fixture()
def oracle(block_oracle, mock_lz_relay, mock_cre_relay, dev_deployer):
    """Oracle with both relays registered as committers, which the hub's constructor requires."""
    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(mock_lz_relay.address, False)
        block_oracle.add_committer(mock_cre_relay.address, False)
        block_oracle.set_threshold(1)
    return block_oracle


@pytest.fixture()
def hub(dev_deployer, oracle, mock_lz_relay, mock_cre_relay, hub_deployer):
    with boa.env.prank(dev_deployer):
        return hub_deployer.deploy(
            oracle.address,
            mock_lz_relay.address,
            mock_cre_relay.address,
            BASE_FEE,
            FEE_PER_TARGET,
            FEE_MULTIPLIER_BPS,
            BASE_ON_REPORT_GAS,
            CCIP_SEND_GAS,
        )
