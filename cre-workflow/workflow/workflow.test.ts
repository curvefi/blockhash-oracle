import { describe, expect } from 'bun:test'
import { hexToBytes, TxStatus, type Runtime } from '@chainlink/cre-sdk'
import { EvmMock, newTestRuntime, test } from '@chainlink/cre-sdk/test'
import { encodeAbiParameters, parseAbiParameters, toEventSelector, type Address } from 'viem'
import { type MainnetBlockViewMock, newMainnetBlockViewMock } from '../contracts/evm/ts/generated/MainnetBlockView_mock'
import { initWorkflow, onBlockhashRequested, onNewBlock, REQUESTED_EVENT_SIGNATURE } from './workflow'
import type { ResultPayload } from './types/types'

const CHAIN_SELECTOR = 16015286601757825753n // ethereum-testnet-sepolia

const BLOCK_VIEW_ADDRESS = '0x0000000000000000000000000000000000000001' as Address
const RELAY_ADDRESS = '0x0000000000000000000000000000000000000002' as Address
const AUTHORIZED_KEY = '0x0000000000000000000000000000000000000003' as Address
const HUB_ADDRESS = '0x0000000000000000000000000000000000000004' as Address

const BLOCK_NUMBER = 21000000n
const REAL_BLOCKHASH = `0x${'ab'.repeat(32)}` as `0x${string}`
const ZERO_BLOCKHASH = `0x${'00'.repeat(32)}` as `0x${string}`

type WriteReportHandler = NonNullable<EvmMock['writeReport']>

const makeConfig = () => ({
	authorizedEVMAddress: AUTHORIZED_KEY,
	blockViewChainSelectorName: 'ethereum-testnet-sepolia',
	blockViewContractAddress: BLOCK_VIEW_ADDRESS,
})

const makeHubConfig = () => ({
	...makeConfig(),
	requestHubChainSelectorName: 'ethereum-testnet-sepolia',
	requestHubAddress: HUB_ADDRESS,
	requestHubRelayAddress: RELAY_ADDRESS,
})

const makeHubRuntime = () => {
	const runtime = newTestRuntime()
	;(runtime as any).config = makeHubConfig()
	return runtime as unknown as Runtime<ReturnType<typeof makeHubConfig>>
}

// Only the non-indexed fields land in log.data; request_id and requester are topics
const makeRequestLog = (
	blockNumber = BLOCK_NUMBER,
	selectors: bigint[] = [5009297550715157269n],
	fees: bigint[] = [1000000000000000n],
) => ({
	address: new Uint8Array(20),
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
			onBlockhashRequested(makeHubRuntime() as any, makeRequestLog() as any),
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
			onBlockhashRequested(makeHubRuntime() as any, log as any),
		) as ResultPayload

		expect(result.data[0].targetChainSelectors).toEqual(['1', '2', '3'])
	})

	test('zero blockhash: throws before broadcasting', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, () => [BLOCK_NUMBER, ZERO_BLOCKHASH])

		expect(() => onBlockhashRequested(makeHubRuntime() as any, makeRequestLog() as any))
			.toThrow('unavailable')
	})

	test('failed write: throws with error details', () => {
		const evmMock = EvmMock.testInstance(CHAIN_SELECTOR)
		const blockViewMock = newMainnetBlockViewMock(BLOCK_VIEW_ADDRESS, evmMock)

		setBlockhash(blockViewMock, (bn: unknown) => [bn as bigint, REAL_BLOCKHASH])
		evmMock.writeReport = () => txFail('out of gas')

		expect(() => onBlockhashRequested(makeHubRuntime() as any, makeRequestLog() as any))
			.toThrow('Broadcast error(s)')
	})

	test('unconfigured hub: refuses rather than writing somewhere unintended', () => {
		expect(() => onBlockhashRequested(makeRuntime() as any, makeRequestLog() as any))
			.toThrow('Request hub is not configured')
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
		expect(handlers[1].fn).toBe(onBlockhashRequested)
	})

	test('event signature matches the topic the hub emits', () => {
		expect(toEventSelector(REQUESTED_EVENT_SIGNATURE)).toBe(
			toEventSelector(
				'CREBlockhashRequested(bytes32,address,uint256,uint64[],uint256[],uint256,uint256)',
			),
		)
	})
})
