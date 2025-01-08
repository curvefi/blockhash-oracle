# Blockhash Oracle Contracts

### Description
These contracts are purposed for obtaining latest ethereum mainnet block hash identifiers based on block number. The contracts are deployed on various L1 and L2 networks and make use of simple precompiles for eth block hashes, or LayerZero bridging infrastructure where such precompiles are not available.

### Usage 
Contracts have a view function get_block_hash(uint256 block_number) which returns the ethereum mainnet block hash for the given block number. 

Additionally contracts indicate the information source used to obtain the block hash, as well as last update date.

### Deployments
| Chain | Address | Precompile | LayerZero |
| --- | --- | --- | --- |
| Ethereum | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0f0b0f](https://etherscan.io/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0f0b0f) | Yes | No |
| Arbitrum | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://arbiscan.io/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |
| Base | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://basescan.io/address/SP3G2Q6NY2ZFD9C0VCHZH6PQ7VQXZGK2M2ZQ9KQKV) | Yes | No |
| Fraxtal | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://fraxscan.io/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |
| Optimism | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://optimistic.etherscan.io/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |
| Polygon | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://polygonscan.com/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |
| Gnosis Chain | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://gnosisscan.io/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |
| Binance Smart Chain | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://bscscan.com/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |
| Mantle | [0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f](https://oklink.com/address/0x7e7e7f1b7f3a0b0f0a7ebd3f0b0f0b0f0b0b0b0f) | Yes | No |

### Development details
| Chain | Precompile available | Precompile call | LayerZero available | LayerZero call |
| --- | --- | --- | --- | --- |
| Ethereum | Yes | blockhash() | No | - |
| Arbitrum | Yes | blockhash() | No | - |