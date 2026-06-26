import {
	bytesToHex,
	cre,
	decodeJson,
	getNetwork,
	HTTPPayload,
	TxStatus,
	type Runtime,
} from '@chainlink/cre-sdk'
import {
	type Address,
	encodeAbiParameters,
	parseAbiParameters,
} from 'viem'
import { z } from 'zod'
import type {BroadcastPayload, RequestPayload} from "./types/types";
import {
	MainnetBlockView
} from '../contracts/evm/ts/generated/MainnetBlockView'
import { IReceiver } from '../contracts/evm/ts/generated/IReceiver'

// ─── Config Schema ──────────────────────────────────────────
export const configSchema = z.object({
	authorizedEVMAddress: z.string(),
	blockViewChainSelectorName: z.string(),
	blockViewContractAddress: z.string(),
})
type Config = z.infer<typeof configSchema>

// ─── Broadcast ───────────────────────────────────────────────
export function broadcast(runtime: Runtime<Config>, blockNumber: bigint, blockhash: string, broadcastPayload: BroadcastPayload) {
	const targetChainSelectors: bigint[] = [];
	const targetFees: bigint[] = [];
	for (var chain of broadcastPayload.targetChains) {
		targetChainSelectors.push(BigInt(chain.selector));
		targetFees.push(BigInt(chain.fees));
	}
	const ccipReceiveGasLimit: bigint = BigInt(broadcastPayload.ccipReceiveGasLimit);
	runtime.log(`
		Broadcast using ${broadcastPayload.relay.chainSelectorName},
		to ${targetChainSelectors},
		fees: ${targetFees},
		CRE gas limit: ${broadcastPayload.onReportGasLimit},
		CCIP gas limit: ${ccipReceiveGasLimit}
		`)

	const writeNetwork = getNetwork({
		chainFamily: 'evm',
		chainSelectorName: broadcastPayload.relay.chainSelectorName,
	})
	if (!writeNetwork) throw new Error(`Network not found: ${broadcastPayload.relay.chainSelectorName}`)

	// Prepare relay
	const evmClient = new cre.capabilities.EVMClient(writeNetwork.chainSelector.selector)
	const relay = new IReceiver(evmClient, broadcastPayload.relay.contractAddress as Address)

	// Prepare and send report
	const reportData = encodeAbiParameters(
		parseAbiParameters(
			'uint256 blockNumber,' +
			'bytes32 blockhash,' +
			'uint64[] targetChainSelectors,' +
			'uint256[] targetFees,' +
			'uint256 ccipReceiveGasLimit'),
		[blockNumber, blockhash, targetChainSelectors, targetFees, ccipReceiveGasLimit],
	);

	const writeResult = relay.writeReport(runtime, reportData, {
      gasLimit: broadcastPayload.onReportGasLimit,
    })

	const txHash = bytesToHex(writeResult.txHash || new Uint8Array(32))
	if (writeResult.txStatus !== TxStatus.SUCCESS ||
		writeResult.receiverContractExecutionStatus != 0 ) { // TODO use constant when possible
		// throw new Error(`TX ${txHash} failed: ${writeResult.errorMessage || writeResult.txStatus}`)
		runtime.log(`TX ${txHash} failed: ${writeResult.errorMessage || writeResult.txStatus}`)
	} else {
		runtime.log(`Blockhash committed! TX: ${txHash}`)
	}
}

// ─── New Blockhash Callback ──────────────────────────────────
export const onNewBlock = (
	runtime: Runtime<Config>,
	payload: HTTPPayload,
): string => {
	const config = runtime.config

	// Prepare networks
	const viewNetwork = getNetwork({
		chainFamily: 'evm',
		chainSelectorName: config.blockViewChainSelectorName,
	})
	if (!viewNetwork) throw new Error(`Network not found: ${config.blockViewChainSelectorName}`)

	// // Read HTTP payload
	const blockData = decodeJson(payload.input) as RequestPayload;
	// Fetch blockhash
	const evmClient = new cre.capabilities.EVMClient(viewNetwork.chainSelector.selector)
	const mainnetBlockView = new MainnetBlockView(evmClient, config.blockViewContractAddress as Address)
	let blockNumber, blockhash;
	if (blockData.blockNumber) {
		[blockNumber, blockhash] = mainnetBlockView.getBlockhash0(runtime, BigInt(blockData.blockNumber))
	} else {
		[blockNumber, blockhash] = mainnetBlockView.getBlockhash(runtime)
	}

	runtime.log(`Block number: ${blockNumber}`)

	for (var broadcastPayload of blockData.data) {
		broadcast(runtime, blockNumber, blockhash, broadcastPayload);
	}

	return `Committed block number: ${blockNumber}`
}

// ─── Workflow Init ──────────────────────────────────────────
export function initWorkflow(config: Config) {
  	const http = new cre.capabilities.HTTPCapability();

	return [
		cre.handler(
			http.trigger({
				authorizedKeys: [
					{
						type: "KEY_TYPE_ECDSA_EVM",
						publicKey: config.authorizedEVMAddress,
					},
        		],}),
			onNewBlock,
		),
	]
}
