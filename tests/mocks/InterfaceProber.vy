# pragma version 0.4.3
"""
@notice A contract caller that, when paid, asks the payer whether it supports an interface
        the way ERC165Checker does (a 30k-gas staticcall) and records the answer
"""

interface_id: bytes4
answer: public(bool)


@deploy
def __init__(_interface_id: bytes4):
    self.interface_id = _interface_id


@external
@payable
def __default__():
    ok: bool = False
    out: Bytes[32] = b""
    ok, out = raw_call(
        msg.sender,
        abi_encode(self.interface_id, method_id=method_id("supportsInterface(bytes4)")),
        max_outsize=32,
        gas=30_000,
        is_static_call=True,
        revert_on_failure=False,
    )
    if ok and len(out) == 32:
        self.answer = abi_decode(out, bool)


@external
@payable
def execute(_target: address, _data: Bytes[4096]):
    raw_call(_target, _data, value=msg.value)
