# Curve Block Oracle

## Overview

The Curve Block Oracle is a decentralized system for securely providing Ethereum mainnet block hashes and state roots to other blockchain networks. This enables permissionless storage proofs and cross-chain verification of Ethereum state.

## Key Features

- **Permissionless Access**: Anyone can use the oracle to verify Ethereum state on supported chains
- **Multi-Chain Support**: Deployed across 20+ EVM-compatible chains
- **Decentralized Security**: Multi-committer consensus mechanism with threshold validation
- **LayerZero Integration**: Leverages LayerZero for secure cross-chain messaging
- **Storage Proof Ready**: Provides block hashes and state roots needed for Ethereum storage proofs

## How It Works

### Architecture

The system consists of four main components:

1. **MainnetBlockView** (Ethereum only)
   - Contract: `0xb10CfacE69cc0B7F1AE0Dc8E6aD186914f6e7EEA`
   - Provides aged block hashes (65+ blocks old) to prevent reorg issues
   - Called off-chain via LayerZero's lzRead functionality

2. **BlockOracle** (All supported chains)
   - Contract: `0xb10cface69821Ff7b245Cf5f28f3e714fDbd86b8`
   - Stores confirmed block hashes and decoded block headers
   - Uses threshold-based consensus (currently 1 committer: LZBlockRelay)
   - Immutable once applied

3. **LZBlockRelay** (All supported chains)
   - Contract: `0xFacEFeeD696BFC0ebe7EaD3FFBb9a56290d31752`
   - Handles cross-chain messaging via LayerZero
   - Commits block hashes to BlockOracle
   - Supports read-enabled chains for direct Ethereum queries

4. **HeaderVerifier** (All supported chains)
   - Contract: `0xB10CDEC0DE69c88a47c280a97A5AEcA8b0b83385`
   - Decodes RLP-encoded Ethereum block headers
   - Extracts state root, parent hash, and other fields

### Block Hash Flow

1. **Request**: User calls `request_block_hash()` on a read-enabled chain's LZBlockRelay
2. **Read**: LayerZero reads the block hash from MainnetBlockView on Ethereum
3. **Commit**: LZBlockRelay receives the response and commits to BlockOracle
4. **Broadcast**: Optionally broadcasts the block hash to other specified chains
5. **Verify**: Anyone can submit the RLP-encoded header to extract state roots

## Usage

### For Developers

To use block hashes for storage proofs:

```solidity
// Get confirmed block hash
bytes32 blockHash = IBlockOracle(ORACLE_ADDRESS).get_block_hash(blockNumber);

// Get state root for proofs
bytes32 stateRoot = IBlockOracle(ORACLE_ADDRESS).get_state_root(blockNumber);
```

### Requesting Block Hashes

On read-enabled chains (Optimism, Arbitrum, Base):

```python
# 1. Quote fees
read_fee = relay.quote_read_fee(read_gas_limit=200000, value=0)
broadcast_fees = relay.quote_broadcast_fees(target_chains, gas_limit=100000)

# 2. Request block hash
relay.request_block_hash(
    target_chains,
    broadcast_fees,
    lz_receive_gas_limit=100000,
    read_gas_limit=200000,
    block_number=0,  # 0 = latest safe block
    value=read_fee + sum(broadcast_fees)
)
```

### Submitting Block Headers

Anyone can submit headers for confirmed block hashes:

```python
# Get RLP-encoded header from Ethereum
encoded_header = eth.get_block(block_number).rawHeader

# Submit to HeaderVerifier
verifier.submit_block_header(oracle_address, encoded_header)
```

## Deployed Addresses

### Ethereum Mainnet
- MainnetBlockView: `0xb10CfacE69cc0B7F1AE0Dc8E6aD186914f6e7EEA`

### All Other Chains
- BlockOracle: `0xb10cface69821Ff7b245Cf5f28f3e714fDbd86b8`
- LZBlockRelay: `0xFacEFeeD696BFC0ebe7EaD3FFBb9a56290d31752`
- HeaderVerifier: `0xB10CDEC0DE69c88a47c280a97A5AEcA8b0b83385`

### Supported Chains
- Arbitrum, Optimism, Base, Polygon, BSC
- Avalanche, Fantom, Gnosis, Celo, Moonbeam
- Fraxtal, Mantle, Taiko, Sonic, Kava
- Aurora, X Layer, Hyperliquid, Ink, Corn

## Security Model

### Trust Assumptions
- **Curve DAO**: Controls oracle ownership and committer management
- **LayerZero**: Trusted for message delivery and lzRead functionality
- **Threshold Security**: Requires threshold committers to agree on block hashes
- **Chain Security**: System is as secure as the least secure supported chain

### Current Configuration
- Threshold: 1 committer (LZBlockRelay only)
- Read-enabled chains can query Ethereum directly
- Non-read chains rely on broadcasts from read-enabled chains

## Technical Details

### Block Hash Constraints
- Minimum age: 65 blocks (reorg protection)
- Maximum age: 8192 blocks (EVM limit post EIP-2935)
- Default: `block.number - 65` for safety

### Gas Considerations
- Read operations: ~200,000 gas recommended
- Broadcast receive: ~100,000 gas per chain
- Headers must be under 1024 bytes

### RLP Header Decoding
The system extracts:
- `block_hash`: Keccak256 of the header
- `parent_hash`: Previous block reference
- `state_root`: Merkle root for storage proofs
- `receipt_root`: Transaction receipt root
- `block_number`: Block height
- `timestamp`: Block timestamp

## Example Use Cases

1. **Cross-Chain Governance**: Verify mainnet votes on L2s
2. **Bridge Security**: Validate token locks on Ethereum
3. **State Synchronization**: Prove account balances across chains
4. **DeFi Protocols**: Access mainnet price feeds on L2s
5. **Cross-Chain dApps**: Build applications using mainnet state

## Resources

- Example scripts: `/scripts/deployment/`
- Contract source: `/contracts/`
- Security audit: `/report/`

## License

Copyright (c) Curve.Fi, 2025 - all rights reserved

## Contact

Security: security@curve.fi
