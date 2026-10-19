// BroadcastPayload and RequestPayload are inferred from their zod schemas in workflow.ts

export type BroadcastResult = {
  relayChainSelectorName: string;
  targetChainSelectors: string[];
  txHash: string;
  success: boolean;
  message: string | undefined;
};

export type ResultPayload = {
  anySuccess: boolean;
  blockNumber: string;
  data: BroadcastResult[];
}
