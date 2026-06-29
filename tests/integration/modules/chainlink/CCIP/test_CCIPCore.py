"""Test CCIP module core: initialization, router management, and interface support."""

import boa
from conftest import CCIP_ROUTER, CCIP_RECEIVE_GAS_LIMIT


def test_initialization(ccip_module, dev_deployer):
    """Router is set to the constructor argument; deployer is the owner."""
    assert ccip_module.router() == CCIP_ROUTER
    assert ccip_module.owner() == dev_deployer


def test_set_router(ccip_module, dev_deployer):
    """Owner can update the router; new value stored and SetRouter event emitted."""
    new_router = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        ccip_module.set_router(new_router)

    events = ccip_module.get_logs()
    assert ccip_module.router() == new_router
    assert any("SetRouter" in str(e) and new_router in str(e) for e in events)


def test_set_router_unauthorized(ccip_module):
    """Non-owner cannot update the router."""
    stranger = boa.env.generate_address()
    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            ccip_module.set_router(boa.env.generate_address())


def test_supports_interface(ccip_module):
    """supportsInterface returns True for ERC165 and CCIPReceiver; False for unknown."""
    assert ccip_module.supportsInterface(bytes.fromhex("01ffc9a7")) is True  # ERC165
    assert ccip_module.supportsInterface(bytes.fromhex("85572ffb")) is True  # CCIPReceiver
    assert ccip_module.supportsInterface(bytes.fromhex("deadbeef")) is False


def test_build_extra_args(ccip_module):
    """build_extra_args returns non-empty bytes encoding the gas limit."""
    extra_args = ccip_module.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)
    assert isinstance(extra_args, bytes)
    assert len(extra_args) > 0


def test_build_simple_message(ccip_module):
    """build_simple_message constructs a valid EVM2AnyMessage with no token amounts."""
    receiver = boa.env.generate_address()
    data = boa.util.abi.abi_encode("(uint256,bytes32)", (12345, bytes(32)))
    extra_args = ccip_module.build_extra_args(CCIP_RECEIVE_GAS_LIMIT)

    message = ccip_module.build_simple_message(receiver, data, extra_args)

    # token_amounts must be empty (index 2 in the tuple)
    assert message[2] == []
