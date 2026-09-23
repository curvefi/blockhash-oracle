// Code generated — DO NOT EDIT.
import type { Address } from 'viem'
import { addContractMock, type ContractMock, type EvmMock } from '@chainlink/cre-sdk/test'

import { IReceiverABI } from './IReceiver'

export type IReceiverMock = {
} & Pick<ContractMock<typeof IReceiverABI>, 'writeReport'>

export function newIReceiverMock(address: Address, evmMock: EvmMock): IReceiverMock {
  return addContractMock(evmMock, { address, abi: IReceiverABI }) as IReceiverMock
}
