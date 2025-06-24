import boa
from eth_utils import to_checksum_address
import os


def get_contract_bytecode(contract_path: str, args: bytes = None) -> bytes:
    """Get deployment bytecode for contract with constructor args"""
    contract = boa.load_partial(contract_path)
    if args:
        return contract.compiler_data.bytecode + args
    return contract.compiler_data.bytecode


def prepare_mining_command(deployer: str, pattern: str = None) -> str:
    """Prepare command for createXcrunch miner"""
    # Build command
    cmd = f"""# Clone and build the miner:
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
git clone https://github.com/heswithme/createXcrunch.git
cd createXcrunch
git checkout feature/checksum-addresses
cargo build --release

# Run the miner:
./target/release/createxcrunch create3 \\
    --caller {deployer} \\
    --output {pattern[0:10]}.txt"""

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

    with open(salt_file, "r") as f:
        for line in f:
            if "=>" in line:
                try:
                    salt, address = line.strip().split(" => ")
                    checksummed = to_checksum_address(address)
                    print(f"{salt} | {checksummed}")
                    for pattern in ["facefeed", "FACEFEED", "b10cface", "B10CFACE", "FaceFeed"]:
                        if pattern in checksummed:
                            print(f"Found address: {checksummed}, salt: {salt}")

                except Exception:
                    pass
    print("-" * 100 + "\n")


def main(salt_file: str = "scripts/vanity_salt.txt"):
    # Print previously found addresses if file exists
    print_found_addresses(salt_file)

    # Contract details
    # contract_path = "contracts/messengers/LzBlockRelay.vy"
    # contract_path = "contracts/BlockOracle.vy"
    # contract_path = "contracts/MainnetBlockView.vy"
    deployer = "0xb101b2b0aa02b7167D238B98dc1B0b0404a760E8"  # main
    # deployer = "0x73241E98090042A718f7eb1AF07FAD27ff09A3F3" # test

    # Optional: Specify desired address pattern

    # contract_path = "contracts/MainnetBlockView.vy"
    # pattern = "b10cfaceXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

    # contract_path = "contracts/BlockOracle.vy"
    pattern = "b10cfaceXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    # args_encoded = boa.util.abi.abi_encode("(address)", (deployer,))

    # contract_path = "contracts/messengers/LZBlockRelay.vy"
    # pattern = "facefeedXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    # args_encoded = boa.util.abi.abi_encode("(address)", (deployer,))
    # pattern = "b10cdec0deXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

    # Generate command
    command = prepare_mining_command(deployer=deployer, pattern=pattern)

    print(command)


if __name__ == "__main__":
    main()
