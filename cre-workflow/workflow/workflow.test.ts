import { describe, expect } from 'bun:test'
import { hexToBytes, TxStatus, type Runtime } from '@chainlink/cre-sdk'
import { EvmMock, newTestRuntime, test } from '@chainlink/cre-sdk/test'
import { EVM_PB } from '@chainlink/cre-sdk/pb'
import {
	bytesToHex,
	decodeAbiParameters,
	encodeAbiParameters,
	parseAbiParameters,
	toEventSelector,
	type Address,
} from 'viem'
import { type MainnetBlockViewMock, newMainnetBlockViewMock } from '../contracts/evm/ts/generated/MainnetBlockView_mock'
import {
	configSchema,
	encodeReport,
	initWorkflow,
	onBlockhashRequested,
	onNewBlock,
	REPORT_PARAMS,
	REQUESTED_EVENT_SIGNATURE,
} from './workflow'
import vector from '../../tests/fixtures/cre_report_vector.json'
import type { ResultPayload } from './types/types'

const CHAIN_SELECTOR = 16015286601757825753n // ethereum-testnet-sepolia
const CHAIN_ID = 11155111n // ethereum-testnet-sepolia
const BASE_SEPOLIA_SELECTOR = 10344971235874465080n // ethereum-testnet-sepolia-base-1

// The test runtime prefixes each signed report with a fixed-length metadata header
const REPORT_METADATA_HEADER_LENGTH = 109

const BLOCK_VIEW_ADDRESS = '0x0000000000000000000000000000000000000001' as Address
const RELAY_ADDRESS = '0x0000000000000000000000000000000000000002' as Address
const AUTHORIZED_KEY = '0x0000000000000000000000000000000000000003' as Address
const HUB_ADDRESS = '0x0000000000000000000000000000000000000004' as Address
const BASE_RELAY_ADDRESS = '0x0000000000000000000000000000000000000005' as Address

const BLOCK_NUMBER = 21000000n
const REAL_BLOCKHASH = `0x${'ab'.repeat(32)}` as `0x${string}`
const ZERO_BLOCKHASH = `0x${'00'.repeat(32)}` as `0x${string}`

type WriteReportHandler = NonNullable<EvmMock['writeReport']>

const makeConfig = () => ({
	authorizedEVMAddress: AUTHORIZED_KEY,
	blockViewChainSelectorName: 'ethereum-testnet-sepolia',
	blockViewContractAddress: BLOCK_VIEW_ADDRESS,
	requestHubs: [] as { chainSelectorName: string; address: Address; relayAddress: Address }[],
})

const makeHubConfig = (hubs = [HUB_ADDRESS]) => ({
	...makeConfig(),
	requestHubs: hubs.map((address) => ({
		chainSelectorName: 'ethereum-testnet-sepolia',
		address,
		relayAddress: RELAY_ADDRESS,
	})),
})

const makeHubRuntime = (hubs = [HUB_ADDRESS]) => {
	const runtime = newTestRuntime()
	;(runtime as any).config = makeHubConfig(hubs)
	return runtime as unknown as Runtime<ReturnType<typeof makeHubConfig>>
}

const HUB = makeHubConfig().requestHubs[0]

// CreateX puts a hub at the same address on every chain; each chain has its own relay
const makeSameAddressHubConfig = () => ({
	...makeConfig(),
	requestHubs: [
		{ chainSelectorName: 'ethereum-testnet-sepolia', address: HUB_ADDRESS, relayAddress: RELAY_ADDRESS },
		{
			chainSelectorName: 'ethereum-testnet-sepolia-base-1',
			address: HUB_ADDRESS,
			relayAddress: BASE_RELAY_ADDRESS,
		},
	],
})

// Only the non-indexed fields land in log.data; request_id and requester are topics
const makeRequestLog = (
	blockNumber = BLOCK_NUMBER,
	selectors: bigint[] = [5009297550715157269n],
	fees: bigint[] = [1000000000000000n],
	emitter: Address = HUB_ADDRESS,
) => ({
	address: hexToBytes(emitter),
	topics: [new Uint8Array(32), new Uint8Array(32), new Uint8Array(32)],
	data: hexToBytes(
		encodeAbiParameters(
			parseAbiParameters(
				'uint256 blockNumber, uint64[] chainSelectors, uint256[] maxFees, uint256 ccipReceiveGasLimit, uint256 onReportGasLimit',
			),
			[blockNumber, selectors, fees, 200000n, 600000n],
		),
	),
})


const makeRuntime = () => {
	const runtime = newTestRuntime()
	;(runtime as any).config = makeConfig()
	return runtime as unknown as Runtime<ReturnType<typeof makeConfig>>
}

// addContractMock dispatches via ABI function name (snake_case for Vyper contracts)
const setBlockhash = (
	mock: MainnetBlockViewMock,
	fn: (...args: unknown[]) => readonly [bigint, `0x${string}`],
) => {
	;(mock as any)['get_blockhash'] = fn
}

const makeBroadcastPayload = () => ({
	relay: {
		chainSelectorName: 'ethereum-testnet-sepolia',
		contractAddress: RELAY_ADDRESS,
	},
	targetChains: [{ selector: '5009297550715157269', fees: '1000000000000000' }],
	ccipReceiveGasLimit: '200000',
	onReportGasLimit: '500000',
})

const encode = (obj: unknown) => new TextEncoder().encode(JSON.stringify(obj))

const makeHTTPPayload = (blockNumber?: string, broadcastCount = 1) => ({
	input: encode({
		blockNumber,
		data: Array.from({ length: broadcastCount }, makeBroadcastPayload),
	}),
})

const txSuccess = (): ReturnType<WriteReportHandler> => ({
	txStatus: TxStatus.SUCCESS,
	txHash: new Uint8Array(32),
	receiverContractExecutionStatus: 0,
} as unknown as ReturnType<WriteReportHandler>)

const txFail = (message = 'reverted'): ReturnType<WriteReportHandler> => ({
	txStatus: TxStatus.REVERTED,
	txHash: new Uint8Array(32),
	errorMessage: message,
} as unknown as ReturnType<WriteReportHandler>)

describe('onNewBlock', () => {
	test('happy path: latest block committed to all targets', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, REAL_BLOCKHASH])
		evmMock.writeReport = () => txSuccess()

		const runtime = makeRuntime()
		const result = JSON.parse(onNewBlock(runtime, makeHTTPPayload() as any)) as ResultPayload

		expect(result.anySuccess).toBe(true)
		expect(result.blockNumber).toBe(BLOCK_NUMBER.toString())
		expect(result.data).toHaveLength(1)
		expect(result.data[0].success).toBe(true)
	})

	test('specific block number: routes to getBlockhash0 overload', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, (bn: unknown) => [bn as bigint, REAL_BLOCKHASH])
		evmMock.writeReport = () => txSuccess()

		const runtime = makeRuntime()
		const result = JSON.parse(onNewBlock(runtime, makeHTTPPayload('21000000') as any)) as ResultPayload

		expect(result.blockNumber).toBe('21000000')
		expect(result.anySuccess).toBe(true)
	})

	test('zero blockhash: throws before broadcasting', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, ZERO_BLOCKHASH])

		const runtime = makeRuntime()

		expect(() => onNewBlock(runtime, makeHTTPPayload() as any))
			.toThrow('unavailable')
	})

	test('all broadcasts fail: throws with error details', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, REAL_BLOCKHASH])
		evmMock.writeReport = () => txFail('out of gas')

		const runtime = makeRuntime()

		expect(() => onNewBlock(runtime, makeHTTPPayload() as any))
			.toThrow('Broadcast error(s)')
	})

	test('partial failure: returns JSON with anySuccess true', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, REAL_BLOCKHASH])

		let callCount = 0
		evmMock.writeReport = () => {
			callCount++
			return callCount === 1 ? txSuccess() : txFail()
		}

		const runtime = makeRuntime()
		const result = JSON.parse(onNewBlock(runtime, makeHTTPPayload(undefined, 2) as any)) as ResultPayload

		expect(result.anySuccess).toBe(true)
		expect(result.data[0].success).toBe(true)
		expect(result.data[1].success).toBe(false)
	})
})

describe('onBlockhashRequested', () => {
	test('happy path: decodes the log and broadcasts to its targets', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, (bn: unknown) => [bn as bigint, REAL_BLOCKHASH])
		evmMock.writeReport = () => txSuccess()

		const result = JSON.parse(
			onBlockhashRequested(makeHubRuntime() as any, makeRequestLog() as any, HUB),
		) as ResultPayload

		expect(result.anySuccess).toBe(true)
		expect(result.blockNumber).toBe(BLOCK_NUMBER.toString())
		expect(result.data[0].targetChainSelectors).toEqual(['5009297550715157269'])
	})

	test('carries every target from the log through to the broadcast', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, (bn: unknown) => [bn as bigint, REAL_BLOCKHASH])
		evmMock.writeReport = () => txSuccess()

		const log = makeRequestLog(BLOCK_NUMBER, [1n, 2n, 3n], [10n, 20n, 30n])
		const result = JSON.parse(
			onBlockhashRequested(makeHubRuntime() as any, log as any, HUB),
		) as ResultPayload

		expect(result.data[0].targetChainSelectors).toEqual(['1', '2', '3'])
	})

	test('zero blockhash: throws before broadcasting', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, ZERO_BLOCKHASH])

		expect(() => onBlockhashRequested(makeHubRuntime() as any, makeRequestLog() as any, HUB))
			.toThrow('unavailable')
	})

	test('failed write: throws with error details', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, (bn: unknown) => [bn as bigint, REAL_BLOCKHASH])
		evmMock.writeReport = () => txFail('out of gas')

		expect(() => onBlockhashRequested(makeHubRuntime() as any, makeRequestLog() as any, HUB))
			.toThrow('Broadcast error(s)')
	})

	test('same hub address on two chains: each trigger answers on its own relay', () => {
		const sepoliaMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const baseMock = EvmMock.testInstance(BASE_SEPOLIA_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, sepoliaMock)
		setBlockhash(blockViewMock, (bn: unknown) => [bn as bigint, REAL_BLOCKHASH])

		const writes: { chain: string; receiver: string }[] = []
		sepoliaMock.writeReport = (input) => {
			writes.push({ chain: 'sepolia', receiver: bytesToHex(input.receiver) })
			return txSuccess()
		}
		baseMock.writeReport = (input) => {
			writes.push({ chain: 'base', receiver: bytesToHex(input.receiver) })
			return txSuccess()
		}

		const config = makeSameAddressHubConfig()
		const runtime = newTestRuntime()
		;(runtime as any).config = config
		const [, sepoliaTrigger, baseTrigger] = initWorkflow(config)

		// The two logs are indistinguishable: same emitter, same data, and no chain on the log
		sepoliaTrigger.fn(runtime as any, makeRequestLog() as any)
		baseTrigger.fn(runtime as any, makeRequestLog() as any)

		expect(writes).toEqual([
			{ chain: 'sepolia', receiver: RELAY_ADDRESS.toLowerCase() },
			{ chain: 'base', receiver: BASE_RELAY_ADDRESS.toLowerCase() },
		])
	})
})

describe('initWorkflow', () => {
	test('without a hub: only the HTTP trigger is registered', () => {
		const handlers = initWorkflow(makeConfig())
		expect(handlers).toHaveLength(1)
		expect(handlers[0].fn).toBe(onNewBlock)
	})

	test('with a hub: both triggers are registered, HTTP first', () => {
		const handlers = initWorkflow(makeHubConfig())
		expect(handlers).toHaveLength(2)
		expect(handlers[0].fn).toBe(onNewBlock)
		expect(handlers[1].fn).not.toBe(onNewBlock)
	})

	test('hub triggers wait for SAFE logs, a reorged request would spend relay funds it never paid', () => {
		const [, hubTrigger] = initWorkflow(makeHubConfig())
		expect((hubTrigger.trigger as any).config.confidence).toBe(EVM_PB.ConfidenceLevel.SAFE)
	})

	test('one log trigger per hub, each with its own handler bound to that hub', () => {
		const second = '0x0000000000000000000000000000000000000009' as Address
		const handlers = initWorkflow(makeHubConfig([HUB_ADDRESS, second]))
		expect(handlers).toHaveLength(3)
		expect(handlers[1].fn).not.toBe(handlers[2].fn)
	})

	test('config refuses a repeated (chain, address) hub, it would deliver every request twice', () => {
		const hub = makeHubConfig().requestHubs[0]
		const result = configSchema.safeParse({ ...makeConfig(), requestHubs: [hub, { ...hub }] })
		expect(result.success).toBe(false)
	})

	test('config refuses a sixth hub, cre monitors at most 5 log addresses', () => {
		const hubs = (n: number) =>
			Array.from({ length: n }, (_, i) => `0x${(i + 16).toString(16).padStart(40, '0')}` as Address)
		expect(configSchema.safeParse(makeHubConfig(hubs(5))).success).toBe(true)
		expect(configSchema.safeParse(makeHubConfig(hubs(6))).success).toBe(false)
	})

	test('config accepts one hub address on several chains, the CreateX layout', () => {
		expect(configSchema.safeParse(makeSameAddressHubConfig()).success).toBe(true)
	})

	test('event signature matches the topic the hub emits', () => {
		expect(toEventSelector(REQUESTED_EVENT_SIGNATURE)).toBe(
			toEventSelector(
				'CREBlockhashRequested(bytes32,address,uint256,uint64[],uint256[],uint256,uint256)',
			),
		)
	})
})

describe('report', () => {
	test('encoder reproduces the golden vector the relay decodes', () => {
		const encoded = encodeReport(
			vector.relay as Address,
			BigInt(vector.chainId),
			BigInt(vector.blockNumber),
			vector.blockhash as `0x${string}`,
			vector.targetChainSelectors.map(BigInt),
			vector.targetFees.map(BigInt),
			BigInt(vector.ccipReceiveGasLimit),
		)
		expect(encoded).toBe(vector.report as `0x${string}`)
	})

	test('broadcast signs the relay and its chain id, the forwarder does not sign the receiver', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)
		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, REAL_BLOCKHASH])

		let rawReport: Uint8Array | undefined
		evmMock.writeReport = (input) => {
			rawReport = input.report?.rawReport
			return txSuccess()
		}

		onNewBlock(makeRuntime(), makeHTTPPayload() as any)

		expect(rawReport).toBeDefined()
		const [relay, chainId, blockNumber, blockhash] = decodeAbiParameters(
			REPORT_PARAMS,
			bytesToHex(rawReport!.slice(REPORT_METADATA_HEADER_LENGTH)),
		)
		expect(relay.toLowerCase()).toBe(RELAY_ADDRESS.toLowerCase())
		expect(chainId).toBe(CHAIN_ID)
		expect(blockNumber).toBe(BLOCK_NUMBER)
		expect(blockhash).toBe(REAL_BLOCKHASH)
	})
})
