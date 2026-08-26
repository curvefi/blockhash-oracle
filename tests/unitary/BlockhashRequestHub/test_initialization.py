import boa
import pytest

from conftest import (
    BASE_FEE,
    BASE_ON_REPORT_GAS,
    CCIP_SEND_GAS,
    CRE_DEDUP_WINDOW,
    EMPTY_ADDRESS,
    FEE_MULTIPLIER_BPS,
    FEE_PER_TARGET,
)


def _deploy(hub_deployer, oracle, lz, cre, multiplier=FEE_MULTIPLIER_BPS):
    return hub_deployer.deploy(
        oracle,
        lz,
        cre,
        BASE_FEE,
        FEE_PER_TARGET,
        multiplier,
        BASE_ON_REPORT_GAS,
        CCIP_SEND_GAS,
        CRE_DEDUP_WINDOW,
    )


def test_initialization(hub, dev_deployer, oracle, mock_lz_relay, mock_cre_relay):
    assert hub.owner() == dev_deployer
    assert hub.block_oracle() == oracle.address
    assert hub.lz_relay() == mock_lz_relay.address
    assert hub.cre_relay() == mock_cre_relay.address
    assert hub.base_fee() == BASE_FEE
    assert hub.fee_per_target() == FEE_PER_TARGET
    assert hub.fee_multiplier_bps() == FEE_MULTIPLIER_BPS
    assert hub.base_on_report_gas() == BASE_ON_REPORT_GAS
    assert hub.ccip_send_gas() == CCIP_SEND_GAS
    assert hub.cre_dedup_window() == CRE_DEDUP_WINDOW
    assert hub.RAIL_LZ() == 1
    assert hub.RAIL_CRE() == 2


def test_rejects_empty_oracle(hub_deployer, dev_deployer, mock_lz_relay, mock_cre_relay):
    with boa.env.prank(dev_deployer):
        with boa.reverts("Oracle not set"):
            _deploy(hub_deployer, EMPTY_ADDRESS, mock_lz_relay.address, mock_cre_relay.address)


def test_rejects_multiplier_below_one(
    hub_deployer, dev_deployer, oracle, mock_lz_relay, mock_cre_relay
):
    with boa.env.prank(dev_deployer):
        with boa.reverts("Multiplier below 100%"):
            _deploy(
                hub_deployer,
                oracle.address,
                mock_lz_relay.address,
                mock_cre_relay.address,
                multiplier=9_999,
            )


def test_rejects_relay_that_is_not_a_committer(hub_deployer, dev_deployer, oracle, mock_cre_relay):
    """A relay the oracle will not accept commits from can never make a request land."""
    stranger = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        with boa.reverts("LZ relay not a committer"):
            _deploy(hub_deployer, oracle.address, stranger, mock_cre_relay.address)


def test_rejects_cre_relay_that_is_not_a_committer(
    hub_deployer, dev_deployer, oracle, mock_lz_relay
):
    stranger = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        with boa.reverts("CRE relay not a committer"):
            _deploy(hub_deployer, oracle.address, mock_lz_relay.address, stranger)


def test_a_rail_may_ship_disabled(hub_deployer, dev_deployer, oracle, mock_cre_relay):
    with boa.env.prank(dev_deployer):
        hub = _deploy(hub_deployer, oracle.address, EMPTY_ADDRESS, mock_cre_relay.address)
    assert hub.lz_relay() == EMPTY_ADDRESS


def test_set_relays_rechecks_committership(hub, dev_deployer, mock_cre_relay):
    stranger = boa.env.generate_address()
    with boa.env.prank(dev_deployer):
        with boa.reverts("LZ relay not a committer"):
            hub.set_relays(stranger, mock_cre_relay.address)


def test_set_fees(hub, dev_deployer):
    with boa.env.prank(dev_deployer):
        hub.set_fees(1, 2, 30_000)
    assert hub.base_fee() == 1
    assert hub.fee_per_target() == 2
    assert hub.fee_multiplier_bps() == 30_000


def test_set_fees_rejects_multiplier_below_one(hub, dev_deployer):
    with boa.env.prank(dev_deployer):
        with boa.reverts("Multiplier below 100%"):
            hub.set_fees(1, 2, 9_999)


def test_set_gas_params(hub, dev_deployer):
    with boa.env.prank(dev_deployer):
        hub.set_gas_params(400_000, 200_000)
    assert hub.base_on_report_gas() == 400_000
    assert hub.ccip_send_gas() == 200_000


def test_set_cre_dedup_window(hub, dev_deployer):
    with boa.env.prank(dev_deployer):
        hub.set_cre_dedup_window(56)
    assert hub.cre_dedup_window() == 56


@pytest.mark.parametrize(
    "call",
    [
        lambda h: h.set_relays(EMPTY_ADDRESS, EMPTY_ADDRESS),
        lambda h: h.set_fees(1, 1, 10_000),
        lambda h: h.set_gas_params(1, 1),
        lambda h: h.set_cre_dedup_window(1),
        lambda h: h.withdraw_eth(0),
    ],
)
def test_admin_functions_are_owner_only(hub, alice, call):
    with boa.env.prank(alice):
        with boa.reverts():
            call(hub)
