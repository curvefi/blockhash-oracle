# pragma version 0.4.3
"""
@notice A contract caller: forwards any call, and taking ETH costs it more than send's
        2300-gas stipend. Set accept_eth to False to make it reject ETH outright, and
        burn_rounds to make taking ETH as expensive as a test needs.
"""

accept_eth: public(bool)
received: public(uint256)
burn_rounds: public(uint256)


@deploy
def __init__(_accept_eth: bool):
    self.accept_eth = _accept_eth


@external
def set_burn_rounds(_rounds: uint256):
    self.burn_rounds = _rounds


@external
@payable
def __default__():
    assert self.accept_eth, "Rejects ETH"
    self.received += msg.value  # a storage write, over send's stipend
    x: bytes32 = empty(bytes32)
    for i: uint256 in range(self.burn_rounds, bound=10_000):
        x = keccak256(x)


@external
@payable
def execute(_target: address, _data: Bytes[4096]):
    raw_call(_target, _data, value=msg.value)
