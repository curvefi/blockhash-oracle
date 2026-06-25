# pragma version 0.4.3
# pragma optimize gas
"""
@title CCIP Block Hash Sender
@license MIT
@author Curve Finance
"""

# Import ownership management
from snekmate.auth import ownable

uses: ownable

# https://github.com/smartcontractkit/ccip/blob/ccip-develop/contracts/src/v0.8/ccip/interfaces/IRouterClient.sol
interface Router:
    def getFee(_destinationChainSelector: uint64, _message: EVM2AnyMessage) -> uint256: view
    def ccipSend(_destinationChainSelector: uint64, _message: EVM2AnyMessage) -> bytes32: payable


event SetRouter:
    router: address

event SetReceiver:
    destination_chain_selector: indexed(uint64)
    receiver: address


# https://github.com/smartcontractkit/ccip/blob/ccip-develop/contracts/src/v0.8/ccip/libraries/Client.sol#L7-L10
struct EVMTokenAmount:
    token: address
    amount: uint256

# https://github.com/smartcontractkit/ccip/blob/ccip-develop/contracts/src/v0.8/ccip/libraries/Client.sol#L20-L27
struct EVM2AnyMessage:
    receiver: Bytes[32]
    data: Bytes[MAX_DATA_SIZE]
    token_amounts: DynArray[EVMTokenAmount, 1]
    fee_token: address
    extra_args: Bytes[68]

struct Any2EVMMessage:
    message_id: bytes32
    source_chain_selector: uint64
    sender: Bytes[32]
    data: Bytes[64]
    token_amounts: DynArray[EVMTokenAmount, 1]

# https://etherscan.io/address/0xd0B5Fc9790a6085b048b8Aa1ED26ca2b3b282CF2#code#F9#L30
struct EVMExtraArgsV1:
    gas_limit: uint256
    strict: bool

struct GenericExtraArgsV2:
    gas_limit: uint256
    allow_out_of_order_execution: bool

event SetSender:
    source_chain_selector: indexed(uint64)
    sender: address


EVM_EXTRA_ARGS_V1_TAG: constant(bytes4) = 0x97a657c9
GENERIC_EXTRA_ARGS_V2_TAG: constant(bytes4) = 0x181dcf10
MAX_DATA_SIZE: constant(uint256) = 1024

# @dev Static list of supported ERC165 interface ids
SUPPORTED_INTERFACES: constant(bytes4[2]) = [
    # ERC165 interface ID of ERC165
    0x01ffc9a7,
    # ERC165 interface ID of CCIPReceiver
    0x85572ffb,
]


router: public(address)
selector_to_receiver: public(HashMap[uint64, address])
selector_to_sender: public(HashMap[uint64, address])


@deploy
def __init__(_ccip_router: address):
    self.router = _ccip_router
    log SetRouter(router=_ccip_router)


@payable
@internal
def _transmit(
    _destination_chain_selector: uint64, 
    _message: EVM2AnyMessage,
    _fee: uint256
    ):
    """
    @dev See https://docs.chain.link/ccip/supported-networks/mainnet for chain selectors
    """
    extcall Router(self.router).ccipSend(_destination_chain_selector, _message, value=_fee)


@view
@internal
def _quote(_destination_chain_selector: uint64, message: EVM2AnyMessage) -> uint256:
    return staticcall Router(self.router).getFee(
        _destination_chain_selector,
        message
    )


@internal
@pure
def build_extra_args(gas_limit: uint256) -> Bytes[68]:
    extra_args: Bytes[68] = abi_encode(
        GenericExtraArgsV2(gas_limit=gas_limit, allow_out_of_order_execution=True), 
        method_id=GENERIC_EXTRA_ARGS_V2_TAG
    )
    return extra_args



@internal
@pure
def build_simple_message(receiver: address, data: Bytes[MAX_DATA_SIZE], extra_args: Bytes[68]) -> EVM2AnyMessage:
    message: EVM2AnyMessage = EVM2AnyMessage(
            receiver=abi_encode(receiver),
            data=data,
            token_amounts=empty(DynArray[EVMTokenAmount, 1]),
            fee_token=empty(address),
            extra_args=extra_args
        )
    return message


# @view
# @external
# def quote(_destination_chain_selector: uint64, gas_limit: uint256) -> uint256:
#     extra_args: Bytes[68] = self.build_extra_args(gas_limit)
#     receiver: address = self.selector_to_receiver[_destination_chain_selector]
#     data: Bytes[64] = abi_encode(block.number, max_value(uint256))
#     message: EVM2AnyMessage = self.build_simple_message(receiver, data, extra_args)
#     return staticcall Router(self.router).getFee(
#         _destination_chain_selector,
#         message
#     )


@internal
def _set_receiver(_destination_chain_selector: uint64, _receiver: address):
    """
    @notice Set the receiver for cross chain transactions
    @param _destination_chain_selector The unique CCIP destination chain selector
    @param _receiver The address on the destination chain to transmit messages to
    """

    self.selector_to_receiver[_destination_chain_selector] = _receiver
    log SetReceiver(destination_chain_selector=_destination_chain_selector, receiver=_receiver)


@internal
def _set_sender(_source_chain_selector: uint64, _sender: address):
    """
    @notice Set the sender for cross chain transactions
    @param _source_chain_selector The unique CCIP sorce chain selector
    @param _sender The address on the source chain to receive messages from
    """

    self.selector_to_sender[_source_chain_selector] = _sender
    log SetSender(source_chain_selector=_source_chain_selector, sender=_sender)


@internal
def _set_peer(_chain_selector: uint64, _peer: address):
    """
    @notice Set the receiver and the sender for cross chain transactions
    @param _chain_selector The unique CCIP destination chain selector
    @param _peer The address on the destination chain to transmit messages to and/or receive from
    """

    self._set_sender(_chain_selector, _peer)
    self._set_receiver(_chain_selector, _peer)


@external
def set_router(_ccip_router: address):
    """
    @notice Set the CCIP router
    @dev Necessary for any potential upgrades to the router tech
    """
    ownable._check_owner()

    self.router = _ccip_router
    log SetRouter(router=_ccip_router)


@internal
def _ccipReceive(_message: Any2EVMMessage):
    assert msg.sender == self.router, "Only router"
    # Verify that the message comes from a trusted peer
    peer: address = self.selector_to_sender[_message.source_chain_selector]
    assert peer == abi_decode(_message.sender, address), "Invalid sender"


@view
@external
def supportsInterface(_interface_id: bytes4) -> bool:
    return _interface_id in SUPPORTED_INTERFACES
