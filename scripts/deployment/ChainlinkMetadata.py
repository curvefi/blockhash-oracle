import re
import requests
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime


# Maps our chains.json keys to Chainlink's internal chain name identifiers.
# Source: https://github.com/smartcontractkit/chain-selectors
# These are stable string identifiers, not addresses.
_CHAIN_KEY_TO_CL_NAME: Dict[str, str] = {
    # Mainnets
    "ethereum": "ethereum-mainnet",
    "optimism": "ethereum-mainnet-optimism-1",
    "xdc": "xdc-mainnet",
    "bsc": "binance_smart_chain-mainnet",
    "gnosis": "gnosis_chain-mainnet",
    "unichain": "ethereum-mainnet-unichain-1",
    "polygon": "polygon-mainnet",
    "monad": "monad-mainnet",
    "sonic": "sonic-mainnet",
    "xlayer": "ethereum-mainnet-xlayer-1",
    "tac": "tac-mainnet",
    "fraxtal": "fraxtal-mainnet",
    "hyperliquid": "hyperliquid-mainnet",
    "mantle": "ethereum-mainnet-mantle-1",
    "base": "ethereum-mainnet-base-1",
    "plasma": "plasma-mainnet",
    "arbitrum": "ethereum-mainnet-arbitrum-1",
    "celo": "celo-mainnet",
    "etherlink": "etherlink-mainnet",
    "avalanche": "avalanche-mainnet",
    "ink": "ethereum-mainnet-ink-1",
    "plumephoenix": "plume-mainnet",
    "taiko": "ethereum-mainnet-taiko-1",
    "mp1": "corn-mainnet",
    # Testnets
    "sepolia": "ethereum-testnet-sepolia",
    "base-sepolia": "ethereum-testnet-sepolia-base-1",
    "optimism-sepolia": "ethereum-testnet-sepolia-optimism-1",
    "arbitrum-sepolia": "ethereum-testnet-sepolia-arbitrum-1",
}

# Reverse map: Chainlink chain name → our chain key
_CL_NAME_TO_CHAIN_KEY: Dict[str, str] = {v: k for k, v in _CHAIN_KEY_TO_CL_NAME.items()}


class ChainlinkMetadata:
    """
    Handles Chainlink CCIP and CRE metadata for deployment scripts.

    Mirrors LZMetadata: fetches all data from official Chainlink sources and
    caches it locally in a JSON file. Two sources are used:
      - CCIP router/selector: Chainlink API at CCIP_API_URL
      - CRE forwarder addresses: parsed from the forwarder directory docs page

    JSON structure:
        {
            "ccip": {
                "mainnet": {<raw CCIP API response>},
                "testnet": {<raw CCIP API response>}
            },
            "cre_forwarders": {
                "mainnets": { "arbitrum": "0x...", ... },
                "testnets":  { "sepolia":  "0x...", ... }
            }
        }

    Sources:
        CCIP:          https://docs.chain.link/api/ccip/v1/chains
        CRE forwarders: https://docs.chain.link/cre/guides/workflow/using-evm-client/forwarder-directory-ts
    """

    CCIP_API_URL = "https://docs.chain.link/api/ccip/v1/chains"
    CRE_FORWARDER_DOCS_URL = (
        "https://docs.chain.link/cre/guides/workflow/using-evm-client/forwarder-directory-ts"
    )
    _DEFAULT_FILEPATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "chainlink_metadata.json"
    )

    def __init__(self, filepath: str = ""):
        self.filepath = filepath or self._DEFAULT_FILEPATH
        self.metadata: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Fetch / save / load  (mirrors LZMetadata interface)
    # ------------------------------------------------------------------

    def fetch_metadata(self) -> Dict[str, Any]:
        """Fetch CCIP data from Chainlink API and CRE forwarders from docs page."""
        ccip: Dict[str, Any] = {}
        for env in ("mainnet", "testnet"):
            try:
                resp = requests.get(self.CCIP_API_URL, params={"environment": env}, timeout=15)
                resp.raise_for_status()
                ccip[env] = resp.json()
            except requests.RequestException as e:
                raise Exception(f"Chainlink CCIP API fetch failed ({env}): {e}")

        cre_forwarders = self.fetch_cre_forwarders()

        self.metadata = {"ccip": ccip, "cre_forwarders": cre_forwarders}
        return self.metadata

    def fetch_cre_forwarders(self) -> Dict[str, Any]:
        """
        Parse production CRE forwarder addresses from the Chainlink docs page.
        Returns {"mainnets": {chain_key: address}, "testnets": {chain_key: address}}.
        """
        try:
            resp = requests.get(self.CRE_FORWARDER_DOCS_URL, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"CRE forwarder docs fetch failed: {e}")

        html = resp.text

        # The docs page has two sections: "Simulation Forwarders" and "Production Forwarders".
        # We only want the Production (KeystoneForwarder) section.
        prod_marker = 'id="production-forwarders"'
        prod_idx = html.find(prod_marker)
        if prod_idx == -1:
            # Fallback: search for the text anchor
            prod_idx = html.find("production-forwarders")
        if prod_idx == -1:
            raise ValueError("Could not locate 'Production Forwarders' section in CRE docs page")

        # Extract from production section only (50 kB is more than enough)
        section = html[prod_idx : prod_idx + 50_000]

        # Each table row has <code>cl-chain-name</code> then <code>0xADDR</code> in order.
        cl_names = re.findall(r"<code>([a-z][a-z0-9_\-]+-(?:mainnet|testnet)[^<]*)</code>", section)
        addresses = re.findall(r"<code>(0x[a-fA-F0-9]{40})</code>", section)

        if len(cl_names) != len(addresses):
            raise ValueError(
                f"CRE forwarder parse mismatch: {len(cl_names)} chain names vs {len(addresses)} addresses"
            )

        mainnets: Dict[str, str] = {}
        testnets: Dict[str, str] = {}

        for cl_name, address in zip(cl_names, addresses):
            chain_key = _CL_NAME_TO_CHAIN_KEY.get(cl_name)
            if chain_key is None:
                # Chain not in our chains.json – skip silently
                continue
            if "-testnet" in cl_name:
                testnets[chain_key] = address
            else:
                mainnets[chain_key] = address

        return {"mainnets": mainnets, "testnets": testnets}

    def save_to_file(self) -> None:
        if not self.metadata:
            raise Exception("No metadata to save")
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.metadata, f, indent=4)
        except IOError as e:
            raise Exception(f"File save failed: {e}")

    def load_from_file(self, max_age_hours: int = 168) -> Dict[str, Any]:
        """Load from cache; re-fetch if expired or missing. Default TTL: 7 days."""
        if not os.path.exists(self.filepath):
            return self.fetch_and_save()

        age_seconds = datetime.now().timestamp() - os.path.getmtime(self.filepath)
        if age_seconds > max_age_hours * 3600:
            return self.fetch_and_save()

        with open(self.filepath, "r") as f:
            self.metadata = json.load(f)
        return self.metadata

    def fetch_and_save(self) -> Dict[str, Any]:
        self.fetch_metadata()
        self.save_to_file()
        return self.metadata

    # ------------------------------------------------------------------
    # Query interface  (mirrors LZMetadata.get_chain_metadata)
    # ------------------------------------------------------------------

    def get_chain_metadata(self, chain_key: str, network_type: str = "mainnets") -> Dict[str, Any]:
        """
        Return Chainlink metadata for a chain key (same keys as chains.json).

        Args:
            chain_key:    e.g. "base", "arbitrum"
            network_type: "mainnets" or "testnets"

        Returns:
            {
                "ccip_router":    str | None,  # CCIP router on this chain
                "cre_forwarder":  str | None,  # CRE KeystoneForwarder (None = CRE unsupported)
                "chain_selector": int | None,  # CCIP chain selector (uint64)
                "cl_chain_name":  str | None,  # Chainlink internal chain identifier
            }

        Raises:
            KeyError if the chain has no CCIP entry and no CRE forwarder.
        """
        if not self.metadata:
            self.load_from_file()

        env = "mainnet" if network_type == "mainnets" else "testnet"
        cl_name = _CHAIN_KEY_TO_CL_NAME.get(chain_key)

        ccip_router: Optional[str] = None
        chain_selector: Optional[int] = None

        # API response: {"metadata": {...}, "data": {"evm": {"<chainId>": {...}}}}
        # Each entry has "internalId" matching our _CHAIN_KEY_TO_CL_NAME values.
        evm_data = self.metadata.get("ccip", {}).get(env, {}).get("data", {}).get("evm", {})
        for entry in evm_data.values():
            if entry.get("internalId") == cl_name:
                ccip_router = entry.get("router")
                raw_selector = entry.get("selector")
                if raw_selector is not None:
                    chain_selector = int(raw_selector)
                break

        cre_forwarder: Optional[str] = (
            self.metadata.get("cre_forwarders", {}).get(network_type, {}).get(chain_key)
        )

        if ccip_router is None and cre_forwarder is None:
            raise KeyError(
                f"Chain '{chain_key}' not found in Chainlink metadata "
                f"(no CCIP entry for '{cl_name}' and no CRE forwarder)"
            )

        return {
            "ccip_router": ccip_router,
            "cre_forwarder": cre_forwarder,
            "chain_selector": chain_selector,
            "cl_chain_name": cl_name,
        }


if __name__ == "__main__":
    import sys

    cl = ChainlinkMetadata()
    cl.fetch_and_save()
    print("Fetched and saved Chainlink metadata (CCIP + CRE forwarders).")

    chain = sys.argv[1] if len(sys.argv) > 1 else "base"
    data = cl.get_chain_metadata(chain)
    print(f"\n{chain}:")
    print(json.dumps(data, indent=4))
