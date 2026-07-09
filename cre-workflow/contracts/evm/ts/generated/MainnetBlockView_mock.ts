// Code generated — DO NOT EDIT.
import type { Address } from 'viem'
import { addContractMock, type ContractMock, type EvmMock } from '@chainlink/cre-sdk/test'

import { MainnetBlockViewABI } from './MainnetBlockView'

export type MainnetBlockViewMock = {
  getBlockhash?: () => readonly [bigint, `0x${string}`]
  getBlockhash0?: (blockNumber: bigint) => readonly [bigint, `0x${string}`]
  getBlockhash1?: (blockNumber: bigint, avoidFailure: boolean) => readonly [bigint, `0x${string}`]
} & Pick<ContractMock<typeof MainnetBlockViewABI>, 'writeReport'>

export function newMainnetBlockViewMock(address: Address, evmMock: EvmMock): MainnetBlockViewMock {
  return addContractMock(evmMock, { address, abi: MainnetBlockViewABI }) as MainnetBlockViewMock
}
