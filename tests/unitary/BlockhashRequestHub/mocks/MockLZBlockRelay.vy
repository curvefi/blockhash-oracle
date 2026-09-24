# pragma version 0.4.3

"""
@title Mock LZ Block Relay

@notice Minimal stand-in for LZBlockRelay, covering only what BlockhashRequestHub calls.
Records the arguments of the last request_block_hash so tests can assert the hub forwarded
the right target list, gas limits and pinned block number.

@dev quote_read_fee mirrors the real one in the way that matters here: the value carried back
for the broadcasts is folded into the read quote rather than charged separately.
"""

MAX_N_BROADCAST: constant(uint256) = 32
BPS: constant(uint256) = 10_000

block_oracle: public(address)
peers: public(HashMap[uint32, bytes32])

read_fee: public(uint256)
broadcast_fee: public(uint256)  # charged per configured target
refund_bps: public(uint256)  # share of msg.value handed back, to exercise the hub's refund path

# Last call, for assertions
call_count: public(uint256)
last_value: public(uint256)
last_block_number: public(uint256)
last_lz_gas: public(uint128)
last_read_gas: public(uint128)
last_eids: DynArray[uint32, MAX_N_BROADCAST]
last_fees: DynArray[uint256, MAX_N_BROADCAST]


@view
@external
def get_last_eids() -> DynArray[uint32, MAX_N_BROADCAST]:
    """@dev A public DynArray only generates an indexed getter; tests want the whole list."""
    return self.last_eids


@view
@external
def get_last_fees() -> DynArray[uint256, MAX_N_BROADCAST]:
    return self.last_fees


@deploy
def __init__(_oracle: address, _read_fee: uint256, _broadcast_fee: uint256):
    self.block_oracle = _oracle
    self.read_fee = _read_fee
    self.broadcast_fee = _broadcast_fee


@external
def set_peer(_eid: uint32, _peer: bytes32):
    self.peers[_eid] = _peer


@external
def set_refund_bps(_bps: uint256):
    self.refund_bps = _bps


@view
@external
def quote_read_fee(_read_gas_limit: uint128, _value: uint128) -> uint256:
    return self.read_fee + convert(_value, uint256)


@view
@external
def quote_broadcast_fees(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _lz_receive_gas_limit: uint128,
) -> DynArray[uint256, MAX_N_BROADCAST]:
    fees: DynArray[uint256, MAX_N_BROADCAST] = []
    for eid: uint32 in _target_eids:
        if self.peers[eid] == empty(bytes32):
            fees.append(0)
        else:
            fees.append(self.broadcast_fee)
    return fees


@external
@payable
def request_block_hash(
    _target_eids: DynArray[uint32, MAX_N_BROADCAST],
    _target_fees: DynArray[uint256, MAX_N_BROADCAST],
    _lz_receive_gas_limit: uint128,
    _read_gas_limit: uint128,
    _block_number: uint256,
):
    self.call_count += 1
    self.last_value = msg.value
    self.last_eids = _target_eids
    self.last_fees = _target_fees
    self.last_lz_gas = _lz_receive_gas_limit
    self.last_read_gas = _read_gas_limit
    self.last_block_number = _block_number

    refund: uint256 = msg.value * self.refund_bps // BPS
    if refund > 0:
        raw_call(msg.sender, b"", value=refund)
