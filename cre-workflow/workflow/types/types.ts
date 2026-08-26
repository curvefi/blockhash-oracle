export type BroadcastPayload = {
  relay: {
    chainSelectorName: string;
    contractAddress: string;
  };
  targetChains: [
    {
      selector: string,
      fees: string
    }
  ];
  ccipReceiveGasLimit: string;
  onReportGasLimit: string;
};

export type RequestPayload = {
  blockNumber: string | undefined;
  data: BroadcastPayload[];
}

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
