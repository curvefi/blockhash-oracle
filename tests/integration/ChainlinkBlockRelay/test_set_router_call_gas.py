"""Test for ChainlinkBlockRelay router call gas, set through the exported CCIP setter."""

import pytest
import boa
from conftest import BASE_CHAIN_SELECTOR, CCIP_RECEIVE_GAS_LIMIT


@pytest.mark.mainnet
@pytest.mark.parametrize("call_gas, call_cost", [(2_000_000, 25_000), (500_000, 2_000_000)])
def test_broadcast_holds_back_the_configured_gas(
    forked_env, configured_relay, block_oracle, dev_deployer, block_data, call_gas, call_cost
):
    """The broadcast reserves what set_router_call_gas configured, not a compiled-in figure."""
    with boa.env.prank(dev_deployer):
        configured_relay.set_peers([BASE_CHAIN_SELECTOR], [boa.env.generate_address()])
        configured_relay.eval(
            f"self.received_blocks[{block_data['number']}] = 0x{bytes(block_data['hash']).hex()}"
        )
        block_oracle.admin_apply_block(block_data["number"], block_data["hash"])
    fees = configured_relay.quote_broadcast_fees([BASE_CHAIN_SELECTOR], CCIP_RECEIVE_GAS_LIMIT)
    user = boa.env.generate_address()
    boa.env.set_balance(user, 2 * fees[0])

    def broadcast():
        with boa.env.prank(user):
            configured_relay.broadcast_latest_block(
                [BASE_CHAIN_SELECTOR], fees, CCIP_RECEIVE_GAS_LIMIT, value=fees[0], gas=1_500_000
            )

    with boa.env.anchor():
        broadcast()  # the library's initial values fit in this gas

    with boa.env.prank(dev_deployer):
        configured_relay.set_router_call_gas(call_gas, call_cost)
    with boa.reverts("Not enough gas to transmit"):
        broadcast()
