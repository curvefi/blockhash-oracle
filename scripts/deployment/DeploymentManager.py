"""
Deployment Manager for Blockhash Oracle

Manages deployment state across multiple deployment sessions.
Supports incremental deployments.
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Set


class DeploymentManager:
    """Manages deployment state across multiple deployment sessions"""

    def __init__(self, state_file="deployment_state.json"):
        self.state_file = state_file
        self.load_state()

    def load_state(self):
        """Load deployment state from file"""
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                self.state = json.load(f)
        else:
            self.state = {"deployments": {}, "salts": {}, "deployment_history": []}

    def save_state(self):
        """Save deployment state to file"""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_deployed_contract(
        self, network_type: str, chain: str, contract_type: str
    ) -> Optional[str]:
        """Get deployed contract address"""
        return self.state["deployments"].get(network_type, {}).get(chain, {}).get(contract_type)

    def save_deployment(self, network_type: str, chain: str, contract_type: str, address: str):
        """Save a deployment"""
        if network_type not in self.state["deployments"]:
            self.state["deployments"][network_type] = {}
        if chain not in self.state["deployments"][network_type]:
            self.state["deployments"][network_type][chain] = {}

        self.state["deployments"][network_type][chain][contract_type] = address

        # Add to history
        self.state["deployment_history"].append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "network_type": network_type,
                "chain": chain,
                "contract_type": contract_type,
                "address": address,
            }
        )

        self.save_state()
        logging.info(f"Saved {contract_type} at {address} on {chain}")

    def get_deployed_chains(self, network_type: str) -> Set[str]:
        """Get all chains with deployments"""
        return set(self.state["deployments"].get(network_type, {}).keys())

    def get_all_deployed_contracts(self, network_type: str) -> Dict[str, Dict[str, str]]:
        """Get all deployed contracts for a network type"""
        return self.state["deployments"].get(network_type, {})

    def get_salt(self, network_type: str, salt_type: str) -> Optional[str]:
        """Get saved salt for deterministic deployment"""
        salt = self.state["salts"].get(network_type, {}).get(salt_type)
        # if it starts from 0x, truncate it:
        if salt and salt.startswith("0x"):
            salt = salt[2:]
        return salt

    def save_salt(self, network_type: str, salt_type: str, salt: bytes):
        """Save salt for future deployments"""
        op_dict = self.state["salts"].get(network_type, {})
        op_dict[salt_type] = salt.hex()
        self.state["salts"][network_type] = op_dict
        self.save_state()

    def get_deployment_summary(self, network_type: str) -> Dict:
        """Get deployment summary for a network type"""
        deployments = self.state["deployments"].get(network_type, {})
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "network_type": network_type,
            "total_chains": len(deployments),
            "contracts": deployments,
        }
