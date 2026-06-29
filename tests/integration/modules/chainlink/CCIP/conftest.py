import boa
import pytest

# Real deployed contract addresses on Ethereum mainnet
CCIP_ROUTER = "0x80226fc0Ee2b096224EeAc085Bb9a8cba1146f7D"

# Real CCIP chain selectors for outbound tests (fake selectors cause the real router to revert)
BASE_CHAIN_SELECTOR = 15971525489660198786  # Base mainnet
ARBITRUM_CHAIN_SELECTOR = 4949039107694359620  # Arbitrum One mainnet

# Default gas limit for ccipReceive on destination chain
CCIP_RECEIVE_GAS_LIMIT = 150_000

EMPTY_ADDRESS = boa.eval("empty(address)")


def abi_encode_address(addr: str) -> bytes:
    """ABI-encode an address as Bytes[32] (left-padded with zeros)."""
    return boa.util.abi.abi_encode("address", addr)


def build_any2evm_message(
    source_selector: int,
    sender_address: str,
    data: bytes = b"",
    message_id: bytes = None,
) -> tuple:
    """Build a minimal Any2EVMMessage tuple for _ccipReceive tests."""
    message_id = message_id or bytes(32)
    sender_bytes = abi_encode_address(sender_address)
    return (message_id, source_selector, sender_bytes, data, [])


_CCIP_WRAPPER = """
from snekmate.auth import ownable
from contracts.modules.chainlink import CCIP

initializes: ownable
initializes: CCIP[ownable:=ownable]

exports: (
    ownable.owner,
    ownable.transfer_ownership,
    ownable.renounce_ownership,
)
exports: (
    CCIP.router,
    CCIP.selector_to_receiver,
    CCIP.selector_to_sender,
    CCIP.set_router,
    CCIP.supportsInterface,
)

@deploy
def __init__(_router: address):
    ownable.__init__()
    ownable._transfer_ownership(tx.origin)
    CCIP.__init__(_router)

@external
def set_receiver(_selector: uint64, _receiver: address):
    ownable._check_owner()
    CCIP._set_receiver(_selector, _receiver)

@external
def set_sender(_selector: uint64, _sender: address):
    ownable._check_owner()
    CCIP._set_sender(_selector, _sender)

@external
def set_peer(_selector: uint64, _peer: address):
    ownable._check_owner()
    CCIP._set_peer(_selector, _peer)

@external
def ccipReceive(_message: CCIP.Any2EVMMessage):
    CCIP._ccipReceive(_message)

@external
def transmit(_selector: uint64, _message: CCIP.EVM2AnyMessage, _fee: uint256):
    CCIP._transmit(_selector, _message, _fee)

@view
@external
def quote(_selector: uint64, _message: CCIP.EVM2AnyMessage) -> uint256:
    return CCIP._quote(_selector, _message)

@pure
@external
def build_extra_args(_gas_limit: uint256) -> Bytes[68]:
    return CCIP.build_extra_args(_gas_limit)

@pure
@external
def build_simple_message(
    _receiver: address,
    _data: Bytes[CCIP.MAX_DATA_SIZE],
    _extra_args: Bytes[68],
) -> CCIP.EVM2AnyMessage:
    return CCIP.build_simple_message(_receiver, _data, _extra_args)
"""


@pytest.fixture()
def rpc_url(drpc_api_key):
    """Override parent conftest's rpc_url: always fork Ethereum mainnet."""
    return f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={drpc_api_key}"


@pytest.fixture()
def ccip_module(dev_deployer):
    """CCIP module wrapper — no fork needed for most tests (no external router calls)."""
    with boa.env.prank(dev_deployer):
        return boa.loads(_CCIP_WRAPPER, CCIP_ROUTER)


@pytest.fixture()
def ccip_module_mainnet(forked_env, dev_deployer):
    """CCIP module wrapper on a forked Ethereum mainnet (real router for quote tests)."""
    with boa.env.prank(dev_deployer):
        return boa.loads(_CCIP_WRAPPER, CCIP_ROUTER)
