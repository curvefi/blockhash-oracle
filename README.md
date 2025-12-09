# Curve Block Oracle
## https://curvefi.github.io/blockhash-oracle/


## 1. Overview

The Curve Block Oracle is a decentralized system for securely providing Ethereum mainnet block hashes and state roots to other blockchain networks. This enables permissionless storage proofs and cross-chain verification of Ethereum state, which is essential for a variety of use cases, including cross-chain governance, bridge security, and DeFi protocols.

The system is designed to be highly reliable and secure, leveraging a multi-committer consensus mechanism and LayerZero's cross-chain messaging protocol. It is currently deployed on over 20 EVM-compatible chains.

## 2. Key Features

- **Permissionless Access**: Anyone can use the oracle to verify Ethereum state on supported chains.
- **Multi-Chain Support**: Deployed across a wide range of EVM-compatible chains.
- **Decentralized Security**: Utilizes a multi-committer consensus mechanism with threshold validation to ensure the integrity of block data.
- **LayerZero Integration**: Leverages LayerZero for secure and efficient cross-chain messaging.
- **Storage Proof Ready**: Provides the necessary block hashes and state roots for Ethereum storage proofs.
- **Resilient Design**: The system is designed to be resilient to reorgs and other network disruptions.

## 3. System Architecture

The Curve Block Oracle consists of four main smart contracts:

1.  **`MainnetBlockView`** (Ethereum only):
    -   **Address**: `0xb10cface00696B1390875DB2a0113B3ab99752a4`
    -   Provides access to historical block hashes on the Ethereum mainnet.
    -   To prevent reorg-related issues, it only returns hashes for blocks that are at least 65 blocks old.
    -   This contract is called off-chain via LayerZero's `lzRead` functionality.

2.  **`BlockOracle`** (All supported chains):
    -   **Address**: `0xb10cface698eBbEeda6Fd1aC3e1687a8a3f5c5Df`
    -   Stores confirmed block hashes and decoded block headers.
    -   Uses a threshold-based consensus mechanism to validate block data. Currently, the threshold is set to 1, with `LZBlockRelay` as the sole committer.
    -   Once a block hash is confirmed, it is immutable.

3.  **`LZBlockRelay`** (All supported chains):
    -   **Address**: `0xfacefeed69e0eb9dB6Ad8Cb0883fC45Df7561Dc2`
    -   Handles cross-chain messaging via LayerZero.
    -   Commits block hashes to the `BlockOracle`.
    -   Supports read-enabled chains for direct queries to Ethereum.

4.  **`HeaderVerifier`** (All supported chains):
    -   **Address**: `0xb10CdEc0dE69a227307053bEbBFd80864B71ec27`
    -   Decodes RLP-encoded Ethereum block headers.
    -   Extracts key information, such as the state root, parent hash, and other fields.

### Data Flow

The process of retrieving and verifying a block hash is as follows:

1.  **Request**: A user initiates a request for a block hash by calling the `request_block_hash()` function on a read-enabled chain's `LZBlockRelay` contract.
2.  **Read**: LayerZero reads the requested block hash from the `MainnetBlockView` contract on the Ethereum mainnet.
3.  **Commit**: The `LZBlockRelay` contract receives the response from LayerZero and commits the block hash to the `BlockOracle`.
4.  **Broadcast**: The `LZBlockRelay` can optionally broadcast the block hash to other specified chains.
5.  **Verify**: Once the block hash is confirmed, anyone can submit the RLP-encoded block header to the `HeaderVerifier` to extract the state root and other data.

## 4. Usage

### For Developers

To use the block hashes for storage proofs, you can interact with the `BlockOracle` contract as follows:

```solidity
// Get the confirmed block hash for a given block number
bytes32 blockHash = IBlockOracle(ORACLE_ADDRESS).get_block_hash(blockNumber);

// Get the state root for storage proofs
bytes32 stateRoot = IBlockOracle(ORACLE_ADDRESS).get_state_root(blockNumber);
```

### Requesting Block Hashes

On read-enabled chains (such as Optimism, Arbitrum, and Base), you can request a block hash using the following steps:

```python
# 1. Quote the required fees
read_fee = relay.quote_read_fee(read_gas_limit=200000, value=0)
broadcast_fees = relay.quote_broadcast_fees(target_chains, gas_limit=100000)

# 2. Request the block hash
relay.request_block_hash(
    target_chains,
    broadcast_fees,
    lz_receive_gas_limit=100000,
    read_gas_limit=200000,
    block_number=0,  # 0 indicates the latest safe block
    value=read_fee + sum(broadcast_fees)
)
```

### Submitting Block Headers

Anyone can submit a block header for a confirmed block hash:

```python
# Get the RLP-encoded header from an Ethereum node
encoded_header = eth.get_block(block_number).rawHeader

# Submit the header to the HeaderVerifier
verifier.submit_block_header(oracle_address, encoded_header)
```

## 5. Deployed Addresses

### Ethereum Mainnet

-   **`MainnetBlockView`**: `0xb10cface00696B1390875DB2a0113B3ab99752a4`

### All Other Chains

-   **`BlockOracle`**: `0xb10cface698eBbEeda6Fd1aC3e1687a8a3f5c5Df`
-   **`LZBlockRelay`**: `0xfacefeed69e0eb9dB6Ad8Cb0883fC45Df7561Dc2`
-   **`HeaderVerifier`**: `0xb10CdEc0dE69a227307053bEbBFd80864B71ec27`

### Supported Chains

The Curve Block Oracle is deployed on the following chains:

-   Ethereum
-   Optimism
-   XDC
-   BSC
-   Gnosis
-   Polygon
-   Sonic
-   XLayer
-   TAC
-   Fantom
-   Fraxtal
-   Hyperliquid
-   Moonbeam
-   Kava
-   Mantle
-   Base
-   Arbitrum
-   Celo
-   Avalanche
-   Ink
-   Plume
-   Taiko
-   Corn
-   Aurora

## 6. Security Model

### Trust Assumptions

-   **Curve DAO**: The Curve DAO controls the ownership of the oracle and the management of committers.
-   **LayerZero**: LayerZero is trusted for message delivery and the `lzRead` functionality.
-   **Threshold Security**: The system requires a threshold of committers to agree on a block hash before it is confirmed.
-   **Chain Security**: The overall security of the system is dependent on the security of the least secure supported chain.

### Current Configuration

-   **Threshold**: 1 committer (with `LZBlockRelay` as the sole committer).
-   **Read-Enabled Chains**: Can query Ethereum directly.
-   **Non-Read-Enabled Chains**: Rely on broadcasts from read-enabled chains.

## 7. Technical Details

### Block Hash Constraints

-   **Minimum Age**: 65 blocks (for reorg protection).
-   **Maximum Age**: 8192 blocks (due to the EVM limit post-EIP-2935).
-   **Default**: `block.number - 65` for safety.

### Gas Considerations

-   **Read Operations**: Approximately 200,000 gas is recommended.
-   **Broadcast Receive**: Approximately 100,000 gas per chain.
-   **Header Size**: Headers must be under 1024 bytes.

### RLP Header Decoding

The system extracts the following fields from the RLP-encoded block header:

-   `block_hash`: The Keccak256 hash of the header.
-   `parent_hash`: A reference to the previous block.
-   `state_root`: The Merkle root for storage proofs.
-   `receipt_root`: The root of the transaction receipt trie.
-   `block_number`: The block height.
-   `timestamp`: The block timestamp.

## 8. Example Use Cases

1.  **Cross-Chain Governance**: Verify mainnet votes on L2s.
2.  **Bridge Security**: Validate token locks on Ethereum.
3.  **State Synchronization**: Prove account balances across different chains.
4.  **DeFi Protocols**: Access mainnet price feeds on L2s.
5.  **Cross-Chain dApps**: Build applications that utilize mainnet state.

## 9. Development

### Prerequisites

-   Python 3.12+
-   [uv](https://github.com/astral-sh/uv)

### Setup

1.  Clone the repository:
    ```bash
    git clone https://github.com/curvefi/blockhash-oracle.git
    cd blockhash-oracle
    ```

2.  Install dependencies:
    ```bash
    uv sync
    ```

### Running Tests

To run the test suite:

```bash
pytest
```

### Deployment

The `scripts/deployment` directory contains scripts for deploying and configuring the contracts. The `DeploymentManager.py` class helps manage the deployment state across multiple sessions.

## 10. Resources

-   **Example Scripts**: `/scripts/deployment/`
-   **Contract Source Code**: `/contracts/`
-   **Security Audit**: `/report/`

## 11. License

Copyright (c) Curve.Fi, 2025 - All Rights Reserved.
