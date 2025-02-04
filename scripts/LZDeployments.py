import requests
import json
import os
from typing import Dict, Any
from datetime import datetime


class LZDeployments:
    # Handles LayerZero deployments metadata fetching and caching
    def __init__(self, filepath: str = "lz_deployments.json"):
        self.api_url = "https://metadata.layerzero-api.com/v1/metadata/deployments"
        self.filepath = filepath
        self.metadata = None

    def fetch_metadata(self) -> Dict[str, Any]:
        # Fresh fetch from LZ API
        try:
            response = requests.get(self.api_url)
            response.raise_for_status()
            self.metadata = response.json()
            return self.metadata
        except requests.RequestException as e:
            raise Exception(f"API fetch failed: {str(e)}")

    def save_to_file(self) -> None:
        # Cache metadata to file
        if not self.metadata:
            raise Exception("No metadata to save")
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.metadata, f, indent=4)
        except IOError as e:
            raise Exception(f"File save failed: {str(e)}")

    def load_from_file(self, max_age_hours: int = 24) -> Dict[str, Any]:
        # Load from cache or fetch if expired/missing
        try:
            if not os.path.exists(self.filepath):
                return self.fetch_and_save()

            is_expired = datetime.now().timestamp() - os.path.getmtime(self.filepath) > (
                max_age_hours * 3600
            )
            if is_expired:
                return self.fetch_and_save()

            with open(self.filepath, "r") as f:
                self.metadata = json.load(f)
            return self.metadata
        except Exception as e:
            raise Exception(f"File load failed: {str(e)}")

    def fetch_and_save(self) -> Dict[str, Any]:
        # Helper: fetch and cache in one go
        self.fetch_metadata()
        self.save_to_file()
        return self.metadata

    def get_chain_metadata(self, chain_key: str) -> Dict[str, Any]:
        # Get chain metadata with v2 deployments and active DVNs
        if not self.metadata:
            self.load_from_file()

        for _, network_data in self.metadata.items():
            if network_data.get("chainKey") != chain_key:
                continue

            # Find v2 deployment
            v2_deployment = next(
                (d for d in network_data["deployments"] if d.get("version") == 2), None
            )
            if not v2_deployment:
                raise ValueError(f"No v2 deployment for {chain_key}")

            # Extract addresses from deployment
            deployment_addresses = {"eid": int(v2_deployment["eid"])}
            deployment_addresses.update(
                {
                    k: v["address"]
                    for k, v in v2_deployment.items()
                    if k not in ["eid", "version", "chainKey", "stage"]
                    and isinstance(v, dict)
                    and "address" in v
                }
            )

            # Filter active v2+ DVNs
            active_dvns = {
                addr: data
                for addr, data in network_data["dvns"].items()
                if not data.get("deprecated", False) and data.get("version", 0) >= 2
            }
            # Transform DVNs into lists
            dvns_list = [{"address": addr, **data} for addr, data in active_dvns.items()]

            dvns_lzread = [
                {"address": addr, **data}
                for addr, data in active_dvns.items()
                if data.get("lzReadCompatible", False)
            ]

            return {
                "metadata": deployment_addresses,
                "dvns": dvns_list,
                "dvns_lzread": dvns_lzread,
                "chainDetails": network_data["chainDetails"],
            }

        raise KeyError(f"Chain {chain_key} not found")


if __name__ == "__main__":
    # Example usage
    lz = LZDeployments()
    chain_data = lz.get_chain_metadata("base-sepolia")
    print(json.dumps(chain_data, indent=4))
