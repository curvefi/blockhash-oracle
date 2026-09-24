"""The relay decodes the shared golden report exactly as the workflow encodes it.

tests/fixtures/cre_report_vector.json is also checked by the workflow's encoder test, so a layout
change on either side fails one of the two.
"""

import json
from pathlib import Path

import boa
import pytest
from conftest import CCIP_ROUTER, CRE_FORWARDER, EMPTY_ADDRESS, EXPECTED_WORKFLOW_ID, VALID_METADATA

VECTOR = json.loads((Path(__file__).parents[2] / "fixtures" / "cre_report_vector.json").read_text())


@pytest.fixture()
def vector_relay(forked_env, block_oracle, dev_deployer):
    """Relay deployed at the vector's address, so the report's destination names it."""
    deployer = boa.load_partial("contracts/messengers/ChainlinkBlockRelay.vy")
    with boa.env.prank(dev_deployer):
        relay = deployer.deploy(CCIP_ROUTER, EMPTY_ADDRESS, override_address=VECTOR["relay"])
        relay.set_block_oracle(block_oracle.address)
        relay.set_expected_workflow_id(EXPECTED_WORKFLOW_ID)
        relay.set_forwarder_address(CRE_FORWARDER)
        block_oracle.add_committer(relay.address, True)
        for selector in VECTOR["targetChainSelectors"]:
            relay.set_receiver(int(selector), boa.env.generate_address())
    boa.env.set_balance(relay.address, sum(int(fee) for fee in VECTOR["targetFees"]))
    return relay


@pytest.mark.mainnet
def test_relay_decodes_golden_report(vector_relay, block_oracle):
    """Every field the relay acts on comes out of the frozen bytes as the vector states."""
    assert boa.env.evm.chain.chain_id == VECTOR["chainId"]

    with boa.env.prank(CRE_FORWARDER):
        vector_relay.onReport(VALID_METADATA, bytes.fromhex(VECTOR["report"][2:]))

    block_hash = bytes.fromhex(VECTOR["blockhash"][2:])
    assert block_oracle.get_block_hash(VECTOR["blockNumber"]) == block_hash

    events = vector_relay.get_logs()
    broadcast = [e for e in events if type(e).__name__ == "BlockHashBroadcast"]
    assert len(broadcast) == 1
    targets = broadcast[0].targets
    selectors = [int(s) for s in VECTOR["targetChainSelectors"]]
    assert [t.chain_selector for t in targets] == selectors
    assert [t.max_fee for t in targets] == [int(f) for f in VECTOR["targetFees"]]

    # The gas limit is never logged, but the fee paid was quoted with it
    paid = [e.fee for e in events if type(e).__name__ == "MessageSent"]
    gas_limit = VECTOR["ccipReceiveGasLimit"]
    assert paid == vector_relay.quote_broadcast_fees(selectors, gas_limit)
    # ...and only that gas limit prices to it, or the check above would prove nothing
    assert paid != vector_relay.quote_broadcast_fees(selectors, gas_limit * 2)
