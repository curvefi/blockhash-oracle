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
      "ccipReceiveGasLimit": "170000",
      "onReportGasLimit": "500000"
    }
  ]
}
```

`blockNumber` is optional — omit it to get `MainnetBlockView`'s default, 65 blocks behind the latest
block (not a finalized one). Production always pins it, so both rails vote on the same block.

## Config

```yaml
authorizedEVMAddress: "0x..."          # ECDSA key allowed to trigger the workflow
blockViewChainSelectorName: "ethereum-mainnet"
blockViewContractAddress: "0xb10cface00696B1390875DB2a0113B3ab99752a4"
requestHubs:                           # optional, one log trigger each; omit for HTTP only
  - chainSelectorName: "ethereum-mainnet-base-1"
    address: "0x..."                   # BlockhashRequestHub, emits CREBlockhashRequested
    relayAddress: "0x..."              # ChainlinkBlockRelay the report is written to
```

Without `requestHubs` the workflow registers only the HTTP trigger, so permissionless hub requests
are never answered. See the limits below for how many hubs a workflow can carry.

Testnets use `ethereum-testnet-sepolia` and the corresponding Sepolia deployment.

## CRE service limits

Chainlink's [service quotas](https://docs.chain.link/cre/service-quotas) bound this workflow
independently of the contracts. Values as read on 2026-09-22; they have changed before (an earlier
reading had HTTP at 1 per 60 s and reports at 5 KB), so re-check them before adding hubs or raising
request volume.

| Quota | Value | What it bounds here |
|---|---|---|
| Log trigger monitored addresses (`PerWorkflow.LogTrigger.FilterAddressLimit`) | 5 | Request hubs: one log trigger each. The config refuses a sixth. Whether the cap is per workflow or per trigger is unclear; confirm with Chainlink before relying on more |
| Triggers per workflow | 10 | 1 HTTP trigger + one per hub |
| Log trigger event rate | 10 per 6 s, burst 10 | Hub requests across all hubs |
| HTTP trigger rate | 1 per 30 s, burst 1 | Operator-triggered deliveries |
| EVM write destination chains | 10 | Relays per HTTP request |
| Report payload | 50 KB | Far above ours: ~2.3 KB with the relay's maximum of 32 targets |
| Gas per EVM write | 10,000,000 | `onReportGasLimit` |
| EVM reads per execution | 15 | One read per delivery today |
| Execution time / capability call | 5 min / 3 min | Relay writes run one after another |
| Concurrent executions per workflow | 50 | Parallel requests |
| Log line | 1 KB | `broadcast()`'s log of selectors and fees can be cut short with many targets; delivery is unaffected |

Executions over a rate quota are queued and retried for up to 10 minutes, then dropped.

## Development

Install dependencies:

```bash
cd workflow && bun install
cd ../contracts && bun install
```

Run tests:

```bash
cd workflow && bun test
```

Simulate against staging:

```bash
cre workflow simulate workflow/ --target testnets-settings --non-interactive --trigger-index 0
```

Targets come from `project.yaml`: `testnets-settings` and `mainnets-settings`.
