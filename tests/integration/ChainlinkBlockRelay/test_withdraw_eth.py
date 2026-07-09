"""Test for ChainlinkBlockRelay withdraw_eth function."""

import pytest
import boa


@pytest.mark.mainnet
def test_withdraw_eth(forked_env, chainlink_block_relay, dev_deployer):
    """Test withdrawing ETH from the contract."""
    user = boa.env.generate_address()

    # Fund the contract (e.g. leftover CCIP fee refunds)
    boa.env.set_balance(chainlink_block_relay.address, 10**18)  # 1 ETH

    # Only owner can withdraw
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            chainlink_block_relay.withdraw_eth(10**17)

    # Cannot withdraw more than balance
    with boa.env.prank(dev_deployer):
        with boa.reverts("Insufficient balance"):
            chainlink_block_relay.withdraw_eth(10**19)  # 10 ETH

    # Valid withdrawal
    owner_balance_before = boa.env.get_balance(dev_deployer)

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.withdraw_eth(10**17)  # 0.1 ETH

    owner_balance_after = boa.env.get_balance(dev_deployer)

    assert owner_balance_after - owner_balance_before == 10**17
    assert boa.env.get_balance(chainlink_block_relay.address) == 9 * 10**17

    # Withdraw full remaining balance
    with boa.env.prank(dev_deployer):
        chainlink_block_relay.withdraw_eth(9 * 10**17)

    assert boa.env.get_balance(chainlink_block_relay.address) == 0
