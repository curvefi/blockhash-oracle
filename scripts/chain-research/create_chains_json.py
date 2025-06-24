#!/usr/bin/env python3
"""
End-to-end script to generate chains.json configuration file.

This script:
1. Parses chain names and RPCs from fe_chains.txt
2. Fetches chain IDs by connecting to RPCs using Web3
3. Maps chains to LayerZero metadata
4. Tests ANKR and DRPC support by attempting connections
5. Determines EVM versions using boa capabilities
6. Generates final chains_new.json with all information
"""

import json
import os
import re
import time
from typing import Dict, List, Optional
from web3 import Web3
import boa
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def parse_fe_chains(filepath: str) -> Dict[str, List[str]]:
    """Parse fe_chains.txt to extract chain names and their RPC URLs."""
    chain_rpcs = {}

    with open(filepath, "r") as f:
        content = f.read()

    # Parse lines like: [ChainId.Arbitrum]:['https://rpc1.com', 'https://rpc2.com']
    pattern = r"\[ChainId\.(\w+)\]:\[(.*)\]"

    for line in content.strip().split("\n"):
        match = re.match(pattern, line)
        if match:
            chain_name = match.group(1)
            rpcs_str = match.group(2)
            # Extract individual RPC URLs
            rpcs = [rpc.strip().strip("'") for rpc in rpcs_str.split(",")]
            chain_rpcs[chain_name] = rpcs

    return chain_rpcs


def get_chain_id(rpcs: List[str]) -> Optional[int]:
    """Connect to RPC endpoints and fetch chain ID."""
    for rpc in rpcs:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 5}))
            if w3.is_connected():
                return w3.eth.chain_id
        except Exception:
            continue
    return None


def load_lz_metadata(filepath: str) -> Dict[str, Dict]:
    """Load and parse LayerZero metadata."""
    with open(filepath, "r") as f:
        lz_data = json.load(f)

    # Build chain ID to LZ key mapping
    chain_id_to_lz = {}

    for key, data in lz_data.items():
        if key.endswith("-mainnet"):
            chain_details = data.get("chainDetails", {})
            if chain_details.get("chainType") == "evm":
                chain_id = chain_details.get("nativeChainId")
                lz_key = chain_details.get("chainKey", key.replace("-mainnet", ""))
                if chain_id:
                    chain_id_to_lz[chain_id] = lz_key

    return chain_id_to_lz


def test_rpc_provider(url: str, expected_chain_id: int) -> bool:
    """Test if an RPC provider supports a chain by verifying chain ID."""
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 3}))
        if w3.is_connected():
            return w3.eth.chain_id == expected_chain_id
    except Exception:
        pass
    return False


def check_ankr_support(chain_name: str, lz_key: str, chain_id: int) -> Optional[str]:
    """Check if ANKR supports the chain and return the URL template."""
    # Use actual ANKR API key from environment or a test key
    test_key = os.environ.get("ANKR_API_KEY", "test123")

    # Special case mappings
    special_mappings = {"mp1": "corn_maizenet", "ethereum": "eth", "sonic": "sonic_mainnet"}

    # Try different ANKR URL patterns
    patterns = []

    if lz_key in special_mappings:
        patterns.append(f"https://rpc.ankr.com/{special_mappings[lz_key]}/{test_key}")

    patterns.extend(
        [
            f"https://rpc.ankr.com/{lz_key.lower()}/{test_key}",
            f"https://rpc.ankr.com/{lz_key.lower()}_mainnet/{test_key}",
            f"https://rpc.ankr.com/{chain_name.lower()}/{test_key}",
        ]
    )

    for pattern in patterns:
        if test_rpc_provider(pattern, chain_id):
            # Return the template without the test key
            return pattern.replace(f"/{test_key}", "/{}")

    return None


def check_drpc_support(chain_name: str, lz_key: str, chain_id: int) -> Optional[str]:
    """Check if DRPC supports the chain and return the URL template."""
    # Try different DRPC URL patterns
    patterns = [
        f"https://lb.drpc.org/ogrpc?network={lz_key.lower()}&dkey=test",
        f"https://lb.drpc.org/ogrpc?network={chain_name.lower()}&dkey=test",
        f"https://{lz_key.lower()}.drpc.org",
        "https://eth.drpc.org" if lz_key == "ethereum" else None,
        "https://bsc.drpc.org" if lz_key == "bsc" else None,
    ]

    for pattern in patterns:
        if pattern and test_rpc_provider(pattern, chain_id):
            if "dkey=" in pattern:
                return pattern.replace("&dkey=test", "&dkey={}")
            return pattern

    return None


def get_evm_version(rpc: str) -> str:
    """Determine EVM version using boa capabilities."""
    try:
        # Setup boa environment
        boa.set_network_env(rpc)

        # Try to get capabilities
        capabilities = boa.env.capabilities.describe_capabilities()

        # Map boa capability strings to EVM versions
        if capabilities == "pre-shanghai":
            return "paris"
        elif capabilities == "shanghai":
            return "shanghai"
        elif capabilities == "cancun":
            return "cancun"
        else:
            return capabilities
    except Exception:
        # Default to paris if capabilities check fails
        return "paris"


def main():
    """Main execution function."""
    print("🚀 Starting chain configuration generation...\n")

    # Step 1: Parse fe_chains.txt
    print("📄 Parsing fe_chains.txt...")
    chain_rpcs = parse_fe_chains("scripts/chain-research/fe_chains.txt")
    print(f"   Found {len(chain_rpcs)} chains")

    # Step 2: Get chain IDs
    print("\n🔍 Fetching chain IDs from RPCs...")
    chain_data = {}

    for chain_name, rpcs in sorted(chain_rpcs.items()):
        print(f"   {chain_name}...", end=" ", flush=True)
        chain_id = get_chain_id(rpcs)

        if chain_id:
            chain_data[chain_name] = {"chain_id": chain_id, "rpcs": rpcs}
            print(f"✓ (ID: {chain_id})")
        else:
            print("✗ (Failed to connect)")

    # Step 3: Load LayerZero metadata
    print("\n📊 Loading LayerZero metadata...")
    chain_id_to_lz = load_lz_metadata("scripts/deployment/lz_metadata.json")
    print(f"   Found {len(chain_id_to_lz)} EVM chains in LZ metadata")

    # Map chains to LZ keys
    for chain_name, data in chain_data.items():
        chain_id = data["chain_id"]
        lz_key = chain_id_to_lz.get(chain_id)
        data["lz_key"] = lz_key

        if not lz_key:
            print(f"   ⚠️  No LZ metadata for {chain_name} (ID: {chain_id})")

    # Step 4: Test RPC providers and get EVM versions
    print("\n🧪 Testing RPC providers and EVM versions...")

    for chain_name, data in sorted(chain_data.items()):
        if not data.get("lz_key"):
            continue

        print(f"\n   {chain_name}:")

        chain_id = data["chain_id"]
        lz_key = data["lz_key"]

        # Test ANKR
        print("      ANKR: ", end="", flush=True)
        ankr_url = check_ankr_support(chain_name, lz_key, chain_id)
        if ankr_url:
            data["ankr"] = ankr_url
            print(f"✓ ({ankr_url})")
        else:
            data["ankr"] = None
            print("✗")

        # Test DRPC
        print("      DRPC: ", end="", flush=True)
        drpc_url = check_drpc_support(chain_name, lz_key, chain_id)
        if drpc_url:
            data["drpc"] = drpc_url
            print(f"✓ ({drpc_url.split('?')[0]}...)")
        else:
            data["drpc"] = None
            print("✗")

        # Get EVM version
        print("      EVM:  ", end="", flush=True)
        # Use first available RPC for EVM version check
        test_rpc = data["rpcs"][0]
        evm_version = get_evm_version(test_rpc)
        data["evm_version"] = evm_version
        print(f"✓ ({evm_version})")

        # Small delay to avoid rate limiting
        time.sleep(0.1)

    # Step 5: Generate final configuration
    print("\n📝 Generating chains_new.json...")

    # Read existing chains.json for testnet configuration
    with open("scripts/deployment/chains.json", "r") as f:
        existing = json.load(f)

    # Build final configuration
    chains_config = {"mainnets": {}, "testnets": existing.get("testnets", {})}

    # Process each chain
    for chain_name, data in sorted(chain_data.items(), key=lambda x: x[1]["chain_id"]):
        lz_key = data.get("lz_key")
        if not lz_key:
            continue

        chain_config = {
            "chain_id": data["chain_id"],
            "evm_version": data.get("evm_version", "paris"),
            "explorer": "https://api.etherscan.io/v2/api",
            "ankr": data.get("ankr"),
            "drpc": data.get("drpc"),
            "public": data["rpcs"][0],  # First public RPC
        }

        # Special cases
        if lz_key == "ethereum":
            chain_config["is_main_chain"] = True

        if lz_key == "xlayer":
            chain_config["explorer"] = (
                "https://www.oklink.com/api/v5/explorer/contract/verify-contract-sourcecode"
            )

        chains_config["mainnets"][lz_key] = chain_config

    # Save the configuration
    with open("scripts/chain-research/chains.json", "w") as f:
        json.dump(chains_config, f, indent=2)

    # Summary
    print(
        f"\n✅ Success! Generated configuration for {len(chains_config['mainnets'])} mainnet chains"
    )

    # Statistics
    ankr_count = sum(1 for c in chains_config["mainnets"].values() if c["ankr"])
    drpc_count = sum(1 for c in chains_config["mainnets"].values() if c["drpc"])

    print("\n📊 Statistics:")
    print(f"   - Total chains: {len(chains_config['mainnets'])}")
    print(f"   - ANKR support: {ankr_count}")
    print(f"   - DRPC support: {drpc_count}")
    print(f"   - Public only: {len(chains_config['mainnets']) - max(ankr_count, drpc_count)}")


if __name__ == "__main__":
    main()
