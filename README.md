# Ethereum Mainnet Block Oracle System

The Ethereum Mainnet Block Oracle System provides decentralized, permissionless access to Ethereum mainnet block hashes and state roots across multiple chains. Governed by Curve DAO, the system leverages LayerZero relayers and a multi-committer consensus mechanism to securely propagate block data in a trust-minimized manner.

## Overview

- **MainnetBlockView:** A contract on Ethereum mainnet that retrieves block hashes for blocks that are safely aged (greater than 64 and less than 256 blocks old). It defaults to `block.number - 65` to avoid reorg risks.
- **BlockOracle:** A non-mainnet-chain contract (e.g., on Arbitrum, Gnosis, etc.) that accepts block header submissions from trusted committers using a threshold-based consensus mechanism. When the required threshold is met, the block data becomes immutable.
- **LayerZero Integration (LZBlockRelay):** Contracts deployed on multiple chains that handle cross-chain messaging. LayerZero relayers, configured with multiple DVNs, enable permissionless broadcasts of block data. For the moment, this relayer is sole commiter of blockhashes.

## System Operation

1. **Block Data Request:**
   Users or relayers trigger a block data request via `request_block_hash`, which initiates a LayerZero read from MainnetBlockView.

2. **Commitment & Validation:**
   Trusted committers submit block headers to the BlockOracle. Once a configurable threshold is reached, the block hash is confirmed and stored permanently.

3. **Broadcasting:**
   Confirmed block data is sent using `broadcast_latest_block` across chains through LayerZero’s messaging system.

4. **Block Header Submission:**
   RLP encoded block headers can be submitted by anyone to the BlockOracle using `submit_block_header`.

## Use Cases

- **State Proofs:**
  Prove mainnet state on sidechains and verify transaction inclusion.


## Deployments & Configuration

Deployments are managed as follows:

| Chain     | Oracle Address | Block Relay Address |
|-----------|----------------|---------------------|
| Ethereum  | [0xB10CFACE40490D798770FEdd104e0a013eD308a6](https://etherscan.io/address/0xB10CFACE40490D798770FEdd104e0a013eD308a6) | N/A (Main view; no block relay) |
| Arbitrum  | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://arbiscan.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://arbiscan.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Polygon   | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://polygonscan.com/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://polygonscan.com/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| BSC       | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://bscscan.com/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://bscscan.com/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Base      | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://basescan.org/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://basescan.org/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Avalanche | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://snowtrace.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://snowtrace.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Optimism  | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://optimistic.etherscan.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://optimistic.etherscan.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Fraxtal   | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://fraxtalscan.com/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://fraxtalscan.com/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Gnosis    | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://gnosisscan.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://gnosisscan.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Sonic     | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://sonicscan.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://sonicscan.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| Ink       | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://inkscan.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://inkscan.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |
| MP1       | [0xb10cface0f31830b780C453031d8E803b442e0A4](https://mp1scan.io/address/0xb10cface0f31830b780C453031d8E803b442e0A4) | [0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F](https://mp1scan.io/address/0xfacefeedcc1a5FDdCa97a20511e6641a5c44370F) |

## Usage Instructions

To request and broadcast block data, follow the recommended process:
1. Choose a broadcaster chain (e.g., Optimism, Arbitrum, Base).
2. Quote the read fee from the chosen broadcaster chain.
3. Check fees for each target chain by calling `quote_broadcast_fees`.
4. Calculate the total fees and then complete the broadcast call.
You can find example use scripts in `scripts/` notebook files.


## Future Enhancements

- **Expanded Committer Network:** Onboard additional trusted committers to further decentralize the consensus process.
- **Fee Optimization:** Enhance fee management for improved efficiency in cross-chain messaging.

## Contact & Support

For additional information or support, please contact the Curve DAO team at **security@curve.fi**.

© Curve.Fi, 2025. All rights reserved.
