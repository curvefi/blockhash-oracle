# Blockhash Oracle Contracts

### Description
These contracts are purposed for obtaining latest ethereum mainnet block hash identifiers based on block number. The contracts are deployed on various L1 and L2 networks and make use of simple precompiles for eth block hashes, or LayerZero bridging infrastructure where such precompiles are not available.

### Preliminary system design

0. Contract MainnetBlockView is deployed on mainnet, providing solely the view on recent (>64, <256) block, returning (block_num, block_hash), and defaulting to block.number-65 (i.e. beacon chain 2 epochs ago)
1. Contract A (come up with name) is deployed on some cheap but trustable l2 chain (arb? opt? base?) on which LZRead is supported. Contract A has permissionless call to request lzRead from MainnetBlockView (transaction 1). After the call, LZ agent calls A.LZRecieve with data returned by MainnetBlockView.
3. Now with updated block data, contract A can use default LZSend functionality that exists on almost every chain to send block number and block hash to other chains.
2a. At LZReceive we can simply store the fresh eth block data, and then translate manually.
2b. At LZReceive we can invoke LZSend to all other chains. However, that will require covering the sending fee. Problematically, LZReceive caller will be LZ agent, so fee should somehow be either passed as additional value on LZRead call (possible to request some value when requesting), or smartly pulled from contract A to cover.
Assume we request message.value to be an overestimated amount of lzsend to all chains. Then, LZReceive is called with message value of this. Then, LZSends can be performed with fractions of this value, and leftover will be returned to refund address. Voila!

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
