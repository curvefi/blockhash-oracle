// Code generated — DO NOT EDIT.
import {
  decodeEventLog,
  decodeFunctionResult,
  encodeEventTopics,
  encodeFunctionData,
  zeroAddress,
} from 'viem'
import type { Address, Hex } from 'viem'
import {
  bytesToHex,
  encodeCallMsg,
  EVMClient,
  hexToBase64,
  LAST_FINALIZED_BLOCK_NUMBER,
  prepareReportRequest,
  type EVMLog,
  type Runtime,
} from '@chainlink/cre-sdk'

export interface DecodedLog<T> extends Omit<EVMLog, 'data'> { data: T }

const encodeTopicValue = (t: Hex | Hex[] | null): string[] => {
  if (t == null) return []
  if (Array.isArray(t)) return t.map(hexToBase64)
  return [hexToBase64(t)]
}





export const MainnetBlockViewABI = [{"stateMutability":"view","type":"function","name":"get_blockhash","inputs":[],"outputs":[{"name":"","type":"uint256"},{"name":"","type":"bytes32"}]},{"stateMutability":"view","type":"function","name":"get_blockhash","inputs":[{"name":"_block_number","type":"uint256"}],"outputs":[{"name":"","type":"uint256"},{"name":"","type":"bytes32"}]},{"stateMutability":"view","type":"function","name":"get_blockhash","inputs":[{"name":"_block_number","type":"uint256"},{"name":"_avoid_failure","type":"bool"}],"outputs":[{"name":"","type":"uint256"},{"name":"","type":"bytes32"}]}] as const

export class MainnetBlockView {
  constructor(
    private readonly client: EVMClient,
    public readonly address: Address,
  ) {}

  getBlockhash(
    runtime: Runtime<unknown>,
  ): readonly [bigint, `0x${string}`] {
    const callData = encodeFunctionData({
      abi: MainnetBlockViewABI,
      functionName: 'get_blockhash' as const,
    })

    const result = this.client
      .callContract(runtime, {
        call: encodeCallMsg({ from: zeroAddress, to: this.address, data: callData }),
        blockNumber: LAST_FINALIZED_BLOCK_NUMBER,
      })
      .result()

    return decodeFunctionResult({
      abi: MainnetBlockViewABI,
      functionName: 'get_blockhash' as const,
      data: bytesToHex(result.data),
    }) as readonly [bigint, `0x${string}`]
  }

  getBlockhash0(
    runtime: Runtime<unknown>,
    blockNumber: bigint,
  ): readonly [bigint, `0x${string}`] {
    const callData = encodeFunctionData({
      abi: MainnetBlockViewABI,
      functionName: 'get_blockhash' as const,
      args: [blockNumber],
    })

    const result = this.client
      .callContract(runtime, {
        call: encodeCallMsg({ from: zeroAddress, to: this.address, data: callData }),
        blockNumber: LAST_FINALIZED_BLOCK_NUMBER,
      })
      .result()

    return decodeFunctionResult({
      abi: MainnetBlockViewABI,
      functionName: 'get_blockhash' as const,
      data: bytesToHex(result.data),
    }) as readonly [bigint, `0x${string}`]
  }

  getBlockhash1(
    runtime: Runtime<unknown>,
    blockNumber: bigint,
    avoidFailure: boolean,
  ): readonly [bigint, `0x${string}`] {
    const callData = encodeFunctionData({
      abi: MainnetBlockViewABI,
      functionName: 'get_blockhash' as const,
      args: [blockNumber, avoidFailure],
    })

    const result = this.client
      .callContract(runtime, {
        call: encodeCallMsg({ from: zeroAddress, to: this.address, data: callData }),
        blockNumber: LAST_FINALIZED_BLOCK_NUMBER,
      })
      .result()

    return decodeFunctionResult({
      abi: MainnetBlockViewABI,
      functionName: 'get_blockhash' as const,
      data: bytesToHex(result.data),
    }) as readonly [bigint, `0x${string}`]
  }

  writeReport(
    runtime: Runtime<unknown>,
    callData: Hex,
    gasConfig?: { gasLimit?: string },
  ) {
    const reportResponse = runtime
      .report(prepareReportRequest(callData))
      .result()

    return this.client
      .writeReport(runtime, {
        receiver: this.address,
        report: reportResponse,
        gasConfig,
      })
      .result()
  }
}
