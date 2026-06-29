# Blockhash Relay — CRE Workflow

HTTP-triggered CRE workflow that reads the latest Ethereum blockhash from `MainnetBlockView` and broadcasts it to multiple destination chains via CCIP.

[Chainlink Runtime Environment documentation](https://docs.chain.link/cre)

## How it works

1. An HTTP trigger fires with a JSON payload listing relay contracts and target chains
2. The workflow reads the blockhash from `MainnetBlockView` on mainnet (or a specific block if provided)
3. The blockhash is ABI-encoded and sent as a report to each relay contract (`ChainlinkBlockRelay`)
4. The relay contract commits the blockhash to its local `BlockOracle`
5. If `targetChains` is set in the payload, the relay then broadcasts the blockhash further to those chains via CCIP

Failures are best-effort: a failed broadcast to one relay does not stop the others. The workflow throws only if every broadcast fails.

## Trigger payload

```json
{
  "blockNumber": "21000000",
  "data": [
    {
      "relay": {
        "chainSelectorName": "ethereum-mainnet",
        "contractAddress": "0x..."
      },
      "targetChains": [
        { "selector": "5009297550715157269", "fees": "1000000000000000" }
      ],
      "ccipReceiveGasLimit": "200000",
      "onReportGasLimit": "500000"
    }
  ]
}
```

`blockNumber` is optional — omit it to use the latest finalized block.

## Config

```yaml
authorizedEVMAddress: "0x..."          # ECDSA key allowed to trigger the workflow
blockViewChainSelectorName: "ethereum-mainnet"
blockViewContractAddress: "0xb10cface00696B1390875DB2a0113B3ab99752a4"
```

Staging uses `ethereum-testnet-sepolia` and the corresponding Sepolia deployment.

## Development

Install dependencies:

```bash
cd workflow && bun install
cd contracts && bun install
```

Run tests:

```bash
cd workflow && bun test
```

Simulate against staging:

```bash
cre workflow simulate workflow/ --target staging-settings --non-interactive --trigger-index 0
```
