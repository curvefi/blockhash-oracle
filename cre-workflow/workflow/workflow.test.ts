import { describe, expect } from 'bun:test'
import { TxStatus, type Runtime } from '@chainlink/cre-sdk'
import { EvmMock, newTestRuntime, test } from '@chainlink/cre-sdk/test'
import type { Address } from 'viem'
import { type MainnetBlockViewMock, newMainnetBlockViewMock } from '../contracts/evm/ts/generated/MainnetBlockView_mock'
import { initWorkflow, onNewBlock } from './workflow'
import type { ResultPayload } from './types/types'

const CHAIN_SELECTOR = 16015286601757825753n // ethereum-testnet-sepolia

const BLOCK_VIEW_ADDRESS = '0x0000000000000000000000000000000000000001' as Address
const RELAY_ADDRESS = '0x0000000000000000000000000000000000000002' as Address
const AUTHORIZED_KEY = '0x0000000000000000000000000000000000000003' as Address

const BLOCK_NUMBER = 21000000n
const REAL_BLOCKHASH = `0x${'ab'.repeat(32)}` as `0x${string}`
const ZERO_BLOCKHASH = `0x${'00'.repeat(32)}` as `0x${string}`

type WriteReportHandler = NonNullable<EvmMock['writeReport']>

const makeConfig = () => ({
	authorizedEVMAddress: AUTHORIZED_KEY,
	blockViewChainSelectorName: 'ethereum-testnet-sepolia',
	blockViewContractAddress: BLOCK_VIEW_ADDRESS,
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

describe('initWorkflow', () => {
	test('returns a single HTTP handler bound to onNewBlock', () => {
		const handlers = initWorkflow(makeConfig())
		expect(handlers).toHaveLength(1)
		expect(handlers[0].fn).toBe(onNewBlock)
	})
})
