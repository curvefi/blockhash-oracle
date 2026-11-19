# pragma version 0.4.3

"""
@title Mock Chainlink Block Relay

@notice Minimal stand-in for ChainlinkBlockRelay, covering only what BlockhashRequestHub calls.
Accepts the hub's CCIP fee push through a payable default, so tests can assert the money moved.

@dev unsupported[] reproduces the one case the real quote_broadcast_fees has that a peer check
does not catch: a receiver is registered but the router has no lane, so the quote comes back 0.
"""

MAX_N_BROADCAST: constant(uint256) = 32

block_oracle: public(address)
selector_to_receiver: public(HashMap[uint64, address])
unsupported: public(HashMap[uint64, bool])

ccip_fee: public(uint256)  # charged per configured target


@deploy
def __init__(_oracle: address, _ccip_fee: uint256):
    self.block_oracle = _oracle
    self.ccip_fee = _ccip_fee


@external
def set_receiver(_chain_selector: uint64, _receiver: address):
    self.selector_to_receiver[_chain_selector] = _receiver


@external
def set_unsupported(_chain_selector: uint64, _unsupported: bool):
    self.unsupported[_chain_selector] = _unsupported


@view
@external
def quote_broadcast_fees(
    _target_chain_selectors: DynArray[uint64, MAX_N_BROADCAST],
    _ccip_receive_gas_limit: uint256,
) -> DynArray[uint256, MAX_N_BROADCAST]:
    fees: DynArray[uint256, MAX_N_BROADCAST] = []
    for selector: uint64 in _target_chain_selectors:
        if self.selector_to_receiver[selector] == empty(address) or self.unsupported[selector]:
            fees.append(0)
        else:
            fees.append(self.ccip_fee)
    return fees


@external
@payable
def __default__():
    pass
