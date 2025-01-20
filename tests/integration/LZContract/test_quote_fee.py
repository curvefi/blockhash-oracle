import boa
from eth_abi import encode

from conftest import LZ_ENDPOINT_ID, LZ_ENDPOINT_BASE_SEPOLIA


def test_quote_fee(forked_env, lz_contract):
    """Test basic quote for default LZ receive option"""
    # Get quote for basic message
    fee = lz_contract.quote_fee(LZ_ENDPOINT_ID, lz_contract.address)
    print(f"\nBasic quote fee: {fee}")

    # Should return non-zero fee
    assert fee > 0, "Fee should not be zero"


def test_quote_fee_different_receivers(forked_env, lz_contract, dev_deployer):
    """Test quotes with different receiver addresses"""
    # Quote to self
    fee_self = lz_contract.quote_fee(LZ_ENDPOINT_ID, lz_contract.address)

    # Quote to deployer
    fee_deployer = lz_contract.quote_fee(LZ_ENDPOINT_ID, dev_deployer)

    print(f"\nFee to self: {fee_self}")
    print(f"Fee to deployer: {fee_deployer}")

    # Fees should be similar for different receivers
    assert abs(fee_self - fee_deployer) < fee_self * 0.1, "Fees should be similar"


def test_quote_fee_revert_case(forked_env, lz_contract):
    """Test cases where quote should revert"""
    # Invalid chain ID
    with boa.reverts():
        lz_contract.quote_fee(0, lz_contract.address)


def test_endpoint_interaction(forked_env, lz_contract, scan_url, scan_api):
    """Compare contract quote with direct endpoint call"""
    # Get quote via contract
    fee_contract = lz_contract.quote_fee(LZ_ENDPOINT_ID, lz_contract.address)
    print(f"\nContract quote: {fee_contract}")

    # Get quote directly from endpoint (known working way)
    endpoint = boa.from_etherscan(
        LZ_ENDPOINT_BASE_SEPOLIA,
        uri=scan_url,
        api_key=scan_api,
    )

    # Same message format as working example
    message = "Hello LayerZero"
    payload = encode(["string"], [message])
    print(f"Message payload: 0x{payload.hex()}")

    # Use exact same options as docs
    options = bytes.fromhex("0003010011010000000000000000000000000000ea60")
    print(f"Options: 0x{options.hex()}")

    # Create params like working example
    params = (
        LZ_ENDPOINT_ID,  # dstEid
        bytes.fromhex("00" * 32),  # receiver
        payload,  # encoded string
        options,  # vanilla OFT options
        False,  # payInLzToken
    )

    # Get direct quote
    fee_direct = endpoint.quote(params, lz_contract.address)
    print("\nDirect quote result:")
    print(f"- Native fee: {fee_direct[0]}")
    print(f"- LZ token fee: {fee_direct[1]}")

    # Compare fees - since we use different messages, they might differ slightly
    assert abs(fee_contract - fee_direct[0]) < fee_contract * 0.1, "Fees differ too much"
