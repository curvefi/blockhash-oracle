# pragma version 0.4.3
"""
@notice A contract caller: forwards any call, and taking ETH costs it more than send's
        2300-gas stipend. Set accept_eth to False to make it reject ETH outright.
"""

accept_eth: public(bool)
received: public(uint256)


@deploy
def __init__(_accept_eth: bool):
    self.accept_eth = _accept_eth


@external
@payable
def __default__():
    assert self.accept_eth, "Rejects ETH"
    self.received += msg.value  # a storage write, over send's stipend


@external
@payable
def execute(_target: address, _data: Bytes[4096]):
    raw_call(_target, _data, value=msg.value)
