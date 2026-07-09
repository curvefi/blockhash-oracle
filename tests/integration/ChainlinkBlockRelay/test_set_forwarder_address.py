"""Test for ChainlinkBlockRelay set_forwarder_address function (via CREReceiver module)."""

import pytest
import boa
from conftest import EMPTY_ADDRESS


@pytest.mark.mainnet
def test_set_forwarder_address(forked_env, chainlink_block_relay, dev_deployer):
    """Owner can set the CRE forwarder (non-owner reverts); the update is stored
    and emits ForwarderAddressUpdated."""
    forwarder = boa.env.generate_address()
    user = boa.env.generate_address()

    # only owner can set
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            chainlink_block_relay.set_forwarder_address(forwarder)

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_forwarder_address(forwarder)

    # event emitted (capture before any view call resets boa's log buffer)
    events = chainlink_block_relay.get_logs()
    assert any("ForwarderAddressUpdated" in str(e) for e in events)

    assert chainlink_block_relay.forwarder_address() == forwarder


@pytest.mark.mainnet
def test_set_forwarder_address_zero_emits_security_warning(
    forked_env, chainlink_block_relay, dev_deployer
):
    """Test that setting forwarder to address(0) emits a SecurityWarning (CRE disabled)."""
    forwarder = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_forwarder_address(forwarder)
        chainlink_block_relay.set_forwarder_address(EMPTY_ADDRESS)

    # Capture logs immediately — a subsequent view call (e.g. the getter below)
    # would reset boa's last-call log buffer.
    events = chainlink_block_relay.get_logs()
    assert any("SecurityWarning" in str(e) for e in events)

    assert chainlink_block_relay.forwarder_address() == EMPTY_ADDRESS


@pytest.mark.mainnet
def test_set_forwarder_address_update(forked_env, chainlink_block_relay, dev_deployer):
    """Test that the forwarder address can be updated multiple times."""
    forwarder_a = boa.env.generate_address()
    forwarder_b = boa.env.generate_address()

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_forwarder_address(forwarder_a)

    assert chainlink_block_relay.forwarder_address() == forwarder_a

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.set_forwarder_address(forwarder_b)

    assert chainlink_block_relay.forwarder_address() == forwarder_b
