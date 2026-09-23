"""Test for LZBlockRelay withdraw_eth function."""

import pytest
import boa

CONTRACT_CALLER = "tests/mocks/ContractCaller.vy"


@pytest.mark.mainnet
def test_withdraw_eth(forked_env, lz_block_relay, dev_deployer):
    """Test withdrawing ETH from the contract."""
    # Generate a non-owner address
    user = boa.env.generate_address()

    # Add balance to contract
    boa.env.set_balance(lz_block_relay.address, 10**18)  # 1 ETH

    # Only owner can withdraw
    with boa.env.prank(user):
        with boa.reverts("ownable: caller is not the owner"):
            lz_block_relay.withdraw_eth(10**17)  # 0.1 ETH

    # Cannot withdraw more than balance
    with boa.env.prank(dev_deployer):
        with boa.reverts("Insufficient balance"):
            lz_block_relay.withdraw_eth(10**19)  # 10 ETH

    # Valid withdrawal
    owner_balance_before = boa.env.get_balance(dev_deployer)

    with boa.env.prank(dev_deployer):
        lz_block_relay.withdraw_eth(10**17)  # 0.1 ETH

    owner_balance_after = boa.env.get_balance(dev_deployer)

    # Check owner received the ETH
    assert owner_balance_after - owner_balance_before == 10**17
    # Check contract balance decreased
    assert boa.env.get_balance(lz_block_relay.address) == 9 * 10**17


@pytest.mark.mainnet
def test_withdraw_eth_to_contract_owner(forked_env, lz_block_relay, dev_deployer):
    """A contract owner (multisig, DAO agent) needing more than send's 2300-gas stipend can withdraw."""
    caller = boa.load(CONTRACT_CALLER, True)
    with boa.env.prank(dev_deployer):
        lz_block_relay.transfer_ownership(caller.address)
    boa.env.set_balance(lz_block_relay.address, 10**18)

    caller.execute(lz_block_relay.address, lz_block_relay.withdraw_eth.prepare_calldata(10**17))

    assert caller.received() == 10**17
    assert boa.env.get_balance(lz_block_relay.address) == 9 * 10**17
