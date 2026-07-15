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


_MOCK_ERC20 = """# pragma version 0.4.3
balanceOf: public(HashMap[address, uint256])

@external
def mint(_to: address, _amount: uint256):
    self.balanceOf[_to] += _amount

@external
def transfer(_to: address, _amount: uint256) -> bool:
    self.balanceOf[msg.sender] -= _amount
    self.balanceOf[_to] += _amount
    return True
"""


@pytest.mark.mainnet
def test_recover_erc20(forked_env, chainlink_block_relay, dev_deployer):
    """Owner can recover ERC20 tokens accidentally sent to the relay."""
    token = boa.loads(_MOCK_ERC20)
    recipient = boa.env.generate_address()
    token.mint(chainlink_block_relay.address, 1000)

    with boa.env.prank(dev_deployer):
        chainlink_block_relay.recover_erc20(token.address, recipient, 1000)

    assert token.balanceOf(chainlink_block_relay.address) == 0
    assert token.balanceOf(recipient) == 1000


@pytest.mark.mainnet
def test_recover_erc20_non_owner_reverts(forked_env, chainlink_block_relay):
    """Non-owner cannot recover ERC20 tokens."""
    token = boa.loads(_MOCK_ERC20)
    stranger = boa.env.generate_address()

    with boa.env.prank(stranger):
        with boa.reverts("ownable: caller is not the owner"):
            chainlink_block_relay.recover_erc20(token.address, stranger, 1)
