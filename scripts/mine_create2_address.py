import boa
from vyper.utils import keccak256
import logging
import time
from typing import Tuple, List, Optional
from ABIs import createX_abi

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# Constants
CREATEX_ADDRESS = "0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed"
MAX_ATTEMPTS = 100_000  # Reduced since we're finding multiple
ADDRESSES_TO_FIND = 10


def setup_env(rpc_url: str) -> None:
    """Initialize boa environment with fork"""
    boa.fork(rpc_url)
    boa.env.enable_fast_mode()


def get_contract_bytecode(contract_path: str, args: bytes = None) -> bytes:
    """Get deployment bytecode for contract with constructor args"""
    contract = boa.load_partial(contract_path)
    if args:
        return contract.compiler_data.bytecode + args
    return contract.compiler_data.bytecode


def compute_create2_address(deployer: str, salt: bytes, bytecode: bytes) -> str:
    """Compute the create2 address for given parameters"""
    with boa.env.prank(deployer):
        createx = boa.loads_abi(createX_abi).at(CREATEX_ADDRESS)
        return createx.computeCreate2Address(salt, keccak256(bytecode))


def mine_addresses(
    contract_path: str,
    init_args: bytes,
    deployer: str,
    guard_bytes: Optional[bytes] = None,
    count: int = ADDRESSES_TO_FIND,
) -> List[Tuple[str, bytes]]:
    """
    Mine multiple create2 addresses
    Returns list of (address, salt) tuples
    """
    bytecode = get_contract_bytecode(contract_path, init_args)
    found_addresses = []
    start_time = time.time()
    print(f"Codehash: {keccak256(bytecode).hex()}")
    for i in range(count):
        # Generate salt
        if guard_bytes:
            random_bytes = bytes.fromhex(hex(i)[2:].zfill(64 - len(guard_bytes) * 2))
            salt = guard_bytes + random_bytes
        else:
            salt = bytes.fromhex(hex(i)[2:].zfill(64))

        # Compute address
        address = compute_create2_address(deployer, salt, bytecode)
        found_addresses.append((address, salt))

    duration = time.time() - start_time
    logging.info(f"\nMined {len(found_addresses)} addresses in {duration:.2f}s")
    return found_addresses


def main():
    # Example usage
    rpc_url = "https://eth-sepolia.public.blastapi.io"
    setup_env(rpc_url)

    # Contract details
    contract_path = "contracts/messengers/LzBlockRelay.vy"
    deployer = "0x73241E98090042A718f7eb1AF07FAD27ff09A3F3"

    # Create guard bytes from deployer address
    # guard_bytes = bytes.fromhex(deployer[2:] + "00")

    # Prepare constructor args
    args_encoded = boa.util.abi.abi_encode("(uint256,address)", (1, deployer))
    # args_encoded = boa.util.abi.abi_encode("(address)", (deployer,))
    # Mine addresses
    addresses = mine_addresses(contract_path, args_encoded, deployer, guard_bytes=None, count=1)

    # Print results in a table format
    print("\nFound Addresses:")
    print("-" * 100)
    print(f"{'Address':<42} | {'Salt':<64}")
    print("-" * 100)
    for addr, salt in addresses:
        print(f"{addr:<42} | {salt.hex()}")


if __name__ == "__main__":
    main()
