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
