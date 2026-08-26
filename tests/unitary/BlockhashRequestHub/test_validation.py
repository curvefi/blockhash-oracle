import boa

from conftest import (
    BASE_CHAIN_SELECTOR,
    BASE_EID,
    BLOCK_HASH,
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


def test_rejects_empty_target_list(hub, alice):
    with boa.reverts("No targets"):
        _request(hub, alice, RAIL_LZ, [], [], lz_cost(1))


def test_rejects_block_not_newer_than_oracle(hub, alice, oracle, dev_deployer):
    with boa.env.prank(dev_deployer):
        oracle.admin_apply_block(PINNED_BLOCK, BLOCK_HASH)

    with boa.reverts("Not newer than oracle"):
        _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1), block_number=PINNED_BLOCK)


def test_accepts_block_above_oracle_height(hub, alice, oracle, dev_deployer):
    with boa.env.prank(dev_deployer):
        oracle.admin_apply_block(PINNED_BLOCK, BLOCK_HASH)

    _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1), block_number=PINNED_BLOCK + 1)


def test_unpinned_cre_request_needs_threshold_one(hub, alice, oracle, dev_deployer):
    """Pinning is required above threshold 1 for either rail, not just for CRE."""
    with boa.env.prank(dev_deployer):
        oracle.set_threshold(2)

    with boa.reverts("Pinned block required above threshold 1"):
        _request(hub, alice, RAIL_CRE, [], CCIP_ONE, cre_cost(1), block_number=0)


def test_unpinned_lz_request_needs_threshold_one(hub, alice, oracle, dev_deployer):
    with boa.env.prank(dev_deployer):
        oracle.add_committer(boa.env.generate_address(), True)
        oracle.add_committer(boa.env.generate_address(), True)
    assert oracle.threshold() > 1

    with boa.reverts("Pinned block required above threshold 1"):
        _request(hub, alice, RAIL_LZ, LZ_ONE, [], lz_cost(1), block_number=0)


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
