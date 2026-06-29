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
	isAddress,
	encodeAbiParameters,
	parseAbiParameters,
} from 'viem'
import { z } from 'zod'
import type {BroadcastPayload, BroadcastResult, RequestPayload, ResultPayload} from "./types/types";
import {
	MainnetBlockView
} from '../contracts/evm/ts/generated/MainnetBlockView'
import { IReceiver } from '../contracts/evm/ts/generated/IReceiver'

// ─── Config Schema ──────────────────────────────────────────
export const evmAddressSchema = z.custom<Address>(
  (val) => typeof val === "string" && isAddress(val),
  { message: "Invalid EVM address. Must be a valid 42-character hex string." }
);

export const configSchema = z.object({
	authorizedEVMAddress: evmAddressSchema,
	blockViewChainSelectorName: z.string(),
	blockViewContractAddress: evmAddressSchema,
})
type Config = z.infer<typeof configSchema>

// ─── Broadcast ───────────────────────────────────────────────
export function broadcast(
	runtime: Runtime<Config>,
	blockNumber: bigint,
	blockhash: `0x${string}`,
	broadcastPayload: BroadcastPayload
): BroadcastResult {
	const result: BroadcastResult = {
		relayChainSelectorName: broadcastPayload.relay.chainSelectorName,
		targetChainSelectors: [],
		txHash: '',
		success: false,
		message: undefined
	}

	const targetChainSelectors: bigint[] = [];
	const targetFees: bigint[] = [];
	for (const chain of broadcastPayload.targetChains) {
		targetChainSelectors.push(BigInt(chain.selector));
		targetFees.push(BigInt(chain.fees));
		result.targetChainSelectors.push(chain.selector);
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
	result.txHash = txHash;
	if (writeResult.txStatus !== TxStatus.SUCCESS ||
		writeResult.receiverContractExecutionStatus != 0 ) { // TODO use constant when possible
		const message = `TX ${txHash} failed: ${writeResult.errorMessage || writeResult.txStatus}`
		runtime.log(message)
		result.message = message
	} else {
		runtime.log(`Blockhash committed! TX: ${txHash}`)
		result.success = true
	}

	return result;
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

	if (blockhash === `0x${'0'.repeat(64)}`) throw new Error(`Blockhash is unavailable for block ${blockNumber}`)


	runtime.log(`Block number: ${blockNumber}`)
	const result: ResultPayload = {
		anySuccess: false,
		blockNumber: blockNumber.toString(),
		data: []
	}

	for (const broadcastPayload of blockData.data) {
		const broadcastResult = broadcast(runtime, blockNumber, blockhash, broadcastPayload);
		if (broadcastResult.success) {
			result.anySuccess = true;
		}
		result.data.push(broadcastResult);
	}

	if (!result.anySuccess) {
		throw new Error(`Broadcast error(s): ${JSON.stringify(result.data)}`)
	}

	return JSON.stringify(result)
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
