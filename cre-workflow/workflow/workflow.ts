import {
	bytesToHex,
	cre,
	decodeJson,
	getNetwork,
	hexToBase64,
	HTTPPayload,
	LATEST_BLOCK_NUMBER,
	TxStatus,
	type Runtime,
} from '@chainlink/cre-sdk'
import type { EVM_PB } from '@chainlink/cre-sdk/pb'
import {
	type Address,
	isAddress,
	decodeAbiParameters,
	encodeAbiParameters,
	parseAbiParameters,
	toEventSelector,
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

export const requestHubSchema = z.object({
	chainSelectorName: z.string(),
	address: evmAddressSchema, // emits CREBlockhashRequested
	relayAddress: evmAddressSchema, // ChainlinkBlockRelay the report is written to
})

export const configSchema = z.object({
	authorizedEVMAddress: evmAddressSchema,
	blockViewChainSelectorName: z.string(),
	blockViewContractAddress: evmAddressSchema,
	// One log trigger per hub; CRE caps a workflow at 5 monitored log addresses
	requestHubs: z.array(requestHubSchema).default([]),
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

// ─── Blockhash Read ──────────────────────────────────────────
export function fetchBlockhash(
	runtime: Runtime<Config>,
	blockNumber?: bigint,
): [bigint, `0x${string}`] {
	const config = runtime.config

	const viewNetwork = getNetwork({
		chainFamily: 'evm',
		chainSelectorName: config.blockViewChainSelectorName,
	})
	if (!viewNetwork) throw new Error(`Network not found: ${config.blockViewChainSelectorName}`)

	const evmClient = new cre.capabilities.EVMClient(viewNetwork.chainSelector.selector)
	const mainnetBlockView = new MainnetBlockView(evmClient, config.blockViewContractAddress as Address)

	// LATEST_BLOCK_NUMBER, not the finalized default: a finalized-tag eth_call sees an older head
	// and can make a pinned block look "too recent" to MainnetBlockView
	const [number, hash] = blockNumber
		? mainnetBlockView.getBlockhash0(runtime, blockNumber, LATEST_BLOCK_NUMBER)
		: mainnetBlockView.getBlockhash(runtime, LATEST_BLOCK_NUMBER)

	if (hash === `0x${'0'.repeat(64)}`) throw new Error(`Blockhash is unavailable for block ${number}`)

	return [number, hash]
}

// ─── Delivery ────────────────────────────────────────────────
// Both triggers do the same work once their payload is decoded: read the pinned blockhash from
// mainnet, then broadcast it to every relay the request names.
function deliver(
	runtime: Runtime<Config>,
	requestedBlock: bigint | undefined,
	payloads: BroadcastPayload[],
): string {
	const [blockNumber, blockhash] = fetchBlockhash(runtime, requestedBlock)
	runtime.log(`Block number: ${blockNumber}`)

	const result: ResultPayload = {
		anySuccess: false,
		blockNumber: blockNumber.toString(),
		data: [],
	}

	for (const payload of payloads) {
		const broadcastResult = broadcast(runtime, blockNumber, blockhash, payload)
		if (broadcastResult.success) result.anySuccess = true
		result.data.push(broadcastResult)
	}

	if (!result.anySuccess) {
		throw new Error(`Broadcast error(s): ${JSON.stringify(result.data)}`)
	}

	return JSON.stringify(result)
}

// ─── HTTP Callback ───────────────────────────────────────────
export const onNewBlock = (runtime: Runtime<Config>, payload: HTTPPayload): string => {
	const blockData = decodeJson(payload.input) as RequestPayload

	return deliver(
		runtime,
		blockData.blockNumber ? BigInt(blockData.blockNumber) : undefined,
		blockData.data,
	)
}

// ─── Request Log Callback ───────────────────────────────────
// BlockhashRequestHub.CREBlockhashRequested; request_id and requester are indexed, the rest is data
export const REQUESTED_EVENT_SIGNATURE =
	'CREBlockhashRequested(bytes32,address,uint256,uint64[],uint256[],uint256,uint256)'

// One literal, not a concatenation: viem infers the decoded tuple's types from the literal only
const REQUESTED_DATA_PARAMS = parseAbiParameters(
	'uint256 blockNumber, uint64[] chainSelectors, uint256[] maxFees, uint256 ccipReceiveGasLimit, uint256 onReportGasLimit'
)

export const onBlockhashRequested = (runtime: Runtime<Config>, log: EVM_PB.Log): string => {
	// Every hub shares this handler, so the emitting address decides which relay to answer on
	const emitter = bytesToHex(log.address).toLowerCase()
	const hub = runtime.config.requestHubs.find((h) => h.address.toLowerCase() === emitter)
	if (!hub) throw new Error(`Log from unknown request hub ${emitter}`)

	const [requestedBlock, chainSelectors, maxFees, ccipReceiveGasLimit, onReportGasLimit] =
		decodeAbiParameters(REQUESTED_DATA_PARAMS, bytesToHex(log.data))

	// The hub pins the block so both rails vote on the same number; the hash itself is read from
	// mainnet here, never taken from the log
	return deliver(runtime, requestedBlock === 0n ? undefined : requestedBlock, [
		{
			relay: { chainSelectorName: hub.chainSelectorName, contractAddress: hub.relayAddress },
			targetChains: chainSelectors.map((selector, i) => ({
				selector: selector.toString(),
				fees: maxFees[i].toString(),
			})),
			ccipReceiveGasLimit: ccipReceiveGasLimit.toString(),
			onReportGasLimit: onReportGasLimit.toString(),
		},
	])
}

// ─── Workflow Init ──────────────────────────────────────────
export function initWorkflow(config: Config) {
	const http = new cre.capabilities.HTTPCapability()

	const httpHandler = cre.handler(
		http.trigger({
			authorizedKeys: [
				{
					type: 'KEY_TYPE_ECDSA_EVM',
					publicKey: config.authorizedEVMAddress,
				},
			],
		}),
		onNewBlock,
	)

	// One trigger per hub: the config pins a single (chain, address) pair each
	const logHandlers = config.requestHubs.map((hub) => {
		const network = getNetwork({ chainFamily: 'evm', chainSelectorName: hub.chainSelectorName })
		if (!network) throw new Error(`Network not found: ${hub.chainSelectorName}`)

		const client = new cre.capabilities.EVMClient(network.chainSelector.selector)

		return cre.handler(
			client.logTrigger({
				// Deployed triggers need base64 addresses and topics; the simulator takes hex
				addresses: [hexToBase64(hub.address)],
				topics: [{ values: [hexToBase64(toEventSelector(REQUESTED_EVENT_SIGNATURE))] }],
				// The log is only a signal - the hash is read fresh from mainnet - so a reorged
				// request costs one wasted execution and never a wrong hash
				confidence: 'CONFIDENCE_LEVEL_LATEST',
			}),
			onBlockhashRequested,
		)
	})

	return [httpHandler, ...logHandlers]
}
