import boa

from conftest import (
    BASE_CHAIN_SELECTOR,
    BASE_EID,
    CCIP_ONE,
    CCIP_RECEIVE_GAS_LIMIT,
    EMPTY_ADDRESS,
    LZ_ONE,
    LZ_READ_GAS_LIMIT,
    LZ_RECEIVE_GAS_LIMIT,
    PINNED_BLOCK,
    RAIL_CRE,
    RAIL_LZ,
    cre_cost,
    lz_cost,
)


def _request(hub, caller, rails, eids, selectors, value, block_number=PINNED_BLOCK):
    with boa.env.prank(caller):
        return hub.request(
            rails,
            eids,
            selectors,
            block_number,
            CCIP_RECEIVE_GAS_LIMIT,
            LZ_RECEIVE_GAS_LIMIT,
            LZ_READ_GAS_LIMIT,
            value=value,
        )


def test_rejects_no_rail(hub, alice):
    with boa.reverts("No rail selected"):
        _request(hub, alice, 0, LZ_ONE, [], lz_cost(1))


def test_rejects_zero_block_number(hub, alice):
    """Both rails must vote on the same number, so the caller has to name one."""
    with boa.reverts("No block number"):
        _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1), block_number=0)


def test_rejects_empty_target_list(hub, alice):
    with boa.reverts("No targets"):
        _request(hub, alice, RAIL_LZ, [], [], lz_cost(1))


def test_rejects_insufficient_value(hub, alice):
    with boa.reverts("Insufficient value"):
        _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1) - 1)


def test_rejects_ccip_target_with_no_route(hub, alice, mock_cre_relay, dev_deployer):
    """A relay quotes 0 for a target it cannot reach, which is the peer check."""
    with boa.env.prank(dev_deployer):
        mock_cre_relay.set_receiver(BASE_CHAIN_SELECTOR, EMPTY_ADDRESS)

    with boa.reverts("No CCIP route"):
        _request(hub, alice, RAIL_CRE, [], CCIP_ONE, cre_cost(1))


def test_rejects_ccip_target_the_router_cannot_serve(hub, alice, mock_cre_relay, dev_deployer):
    """Receiver registered but no live lane: the quote still comes back zero."""
    with boa.env.prank(dev_deployer):
        mock_cre_relay.set_unsupported(BASE_CHAIN_SELECTOR, True)

    with boa.reverts("No CCIP route"):
        _request(hub, alice, RAIL_CRE, [], CCIP_ONE, cre_cost(1))


def test_rejects_lz_target_with_no_route(hub, alice, mock_lz_relay, dev_deployer):
    with boa.env.prank(dev_deployer):
        mock_lz_relay.set_peer(BASE_EID, boa.eval("empty(bytes32)"))

    with boa.reverts("No LayerZero route"):
        _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1))


def test_disabled_rail_is_refused(hub, alice, dev_deployer, mock_cre_relay):
    with boa.env.prank(dev_deployer):
        hub.set_relays(EMPTY_ADDRESS, mock_cre_relay.address)

    with boa.reverts("LayerZero rail disabled"):
        _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1))
