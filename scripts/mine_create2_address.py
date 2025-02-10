import boa
from vyper.utils import keccak256
from eth_utils import to_checksum_address
import os


def get_contract_bytecode(contract_path: str, args: bytes = None) -> bytes:
    """Get deployment bytecode for contract with constructor args"""
    contract = boa.load_partial(contract_path)
    if args:
        return contract.compiler_data.bytecode + args
    return contract.compiler_data.bytecode


def prepare_mining_command(
    contract_path: str, deployer: str, init_args: bytes = None, pattern: str = None
) -> str:
    """Prepare command for createXcrunch miner"""
    # Get bytecode and compute hash
    bytecode = get_contract_bytecode(contract_path, init_args)
    code_hash = keccak256(bytecode).hex()

    # Build command
    cmd = f"""# Clone and build the miner:
git clone https://github.com/HrikB/createXcrunch.git
cd createXcrunch
cargo build --release

# Run the miner:
./target/release/createxcrunch create2 \\
    --caller {deployer} \\
    --code-hash {code_hash}"""

    # Add pattern if specified
    if pattern:
        cmd += f" \\\n    --matching {pattern}"

    return cmd


def print_found_addresses(salt_file: str):
    """Print checksummed addresses from salt file"""
    if not os.path.exists(salt_file):
        return

    print("\nFound addresses from previous mining:")
    print("-" * 100)
    print(f"{'Salt':<66} | {'Checksummed Address':<42}")
    print("-" * 100)

    with open(salt_file, "r") as f:
        for line in f:
            if "=>" in line:
                salt, address = line.strip().split(" => ")
                checksummed = to_checksum_address(address)
                print(f"{salt:<66} | {checksummed}")

    print("-" * 100 + "\n")


def main(salt_file: str = "scripts/vanity_salt.txt"):
    # Print previously found addresses if file exists
    print_found_addresses(salt_file)

    # Contract details
    contract_path = "contracts/messengers/LzBlockRelay.vy"
    contract_path = "contracts/BlockOracle.vy"
    deployer = "0x73241E98090042A718f7eb1AF07FAD27ff09A3F3"

    # Optional: Prepare constructor args if needed
    args_encoded = boa.util.abi.abi_encode("(address)", (deployer,))

    # Optional: Specify desired address pattern
    pattern = "FACEFEEDXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    pattern = "b10cb10cXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    # Generate command
    command = prepare_mining_command(
        contract_path=contract_path, deployer=deployer, init_args=args_encoded, pattern=pattern
    )

    print(command)


if __name__ == "__main__":
    main()
