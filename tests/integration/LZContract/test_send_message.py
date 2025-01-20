import boa

from conftest import LZ_ENDPOINT_ID


def test_send_message_success(forked_env, lz_contract, dev_deployer):
    """
    Test successful message sending with sufficient fee
    """
    boa.env.evm.set_balance(dev_deployer, 10**18)  # 1 ETH
    # Quote the required fee
    required_fee = lz_contract.quote_fee(LZ_ENDPOINT_ID, dev_deployer)

    # Send message with correct fee
    tx = lz_contract.send_message(
        LZ_ENDPOINT_ID, dev_deployer, value=required_fee, sender=dev_deployer
    )

    print(f"Message sent successfully with tx: {tx}")


# def test_send_message_insufficient_fee(forked_env, lz_contract, dev_deployer):
#     """
#     Test sending message with insufficient fee should revert
#     """
#     insufficient_fee = (
#         lz_contract.quote_fee(LZ_ENDPOINT_ID, dev_deployer) // 2
#     )  # Half the required fee

#     with boa.reverts("Invalid fee amount"):
#         lz_contract.send_message(
#             LZ_ENDPOINT_ID, dev_deployer, value=insufficient_fee, sender=dev_deployer
#         )


# def test_send_message_invalid_receiver(forked_env, lz_contract, dev_deployer):
#     """
#     Test sending message with an invalid receiver address
#     """
#     required_fee = lz_contract.quote_fee(LZ_ENDPOINT_ID, dev_deployer)
#     invalid_receiver = "0x0000000000000000000000000000000000000000"

#     with boa.reverts():
#         lz_contract.send_message(
#             LZ_ENDPOINT_ID, invalid_receiver, value=required_fee, sender=dev_deployer
#         )


# def test_send_message_gas_limit_variations(forked_env, lz_contract, dev_deployer):
#     """
#     Test sending messages with different gas limits
#     """
#     for gas_limit in [50000, 100000, 150000]:
#         required_fee = lz_contract.quote_fee(LZ_ENDPOINT_ID, dev_deployer, gas_limit)
#         tx = lz_contract.send_message(
#             LZ_ENDPOINT_ID, dev_deployer, gas_limit, value=required_fee, sender=dev_deployer
#         )
#         assert "MessageSent" in tx.events
#         print(f"Message sent with gas limit {gas_limit} successfully.")


# def test_send_message_pay_in_lz_token(forked_env, lz_contract, dev_deployer):
#     """
#     Ensure the contract rejects LZ token payment option
#     """
#     with boa.reverts("LZ token fee not supported"):
#         lz_contract.send_message(LZ_ENDPOINT_ID, dev_deployer, value=0, sender=dev_deployer)
