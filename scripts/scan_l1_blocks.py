import os
import json
import asyncio
from web3 import AsyncWeb3
from typing import Dict, Tuple
from threading import Lock
import logging
import dotenv

dotenv.load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CONTRACT_ADDRESS = "0x25A9a298494dB90851633E4D74e660C996379Ecc"
ABI = """[{"name":"BlockMismatch","inputs":[{"name":"block_number","type":"uint64","indexed":false},{"name":"stored_hash","type":"bytes32","indexed":false},{"name":"oracle_hash","type":"bytes32","indexed":false},{"name":"stored_timestamp","type":"uint64","indexed":false},{"name":"oracle_timestamp","type":"uint64","indexed":false}],"anonymous":false,"type":"event"},{"stateMutability":"nonpayable","type":"function","name":"fetch_latest_block","inputs":[],"outputs":[]},{"stateMutability":"nonpayable","type":"function","name":"get_block_hash","inputs":[{"name":"block_number","type":"uint64"}],"outputs":[{"name":"","type":"bytes32"}]},{"stateMutability":"nonpayable","type":"function","name":"get_block_timestamp","inputs":[{"name":"block_number","type":"uint64"}],"outputs":[{"name":"","type":"uint64"}]},{"stateMutability":"view","type":"function","name":"peek_l1block_number","inputs":[],"outputs":[{"name":"","type":"uint64"}]},{"stateMutability":"view","type":"function","name":"l1_blocks","inputs":[{"name":"arg0","type":"uint64"}],"outputs":[{"name":"","type":"tuple","components":[{"name":"block_hash","type":"bytes32"},{"name":"block_timestamp","type":"uint64"}]}]},{"stateMutability":"view","type":"function","name":"last_fetched_block","inputs":[],"outputs":[{"name":"","type":"uint64"}]},{"stateMutability":"nonpayable","type":"constructor","inputs":[{"name":"l1block_precompile_address","type":"address"}],"outputs":[]}]"""
DRPC_API_KEY = os.getenv("DRPC_API_KEY")


class BlockScanner:
    def __init__(
        self, op_rpc: str, eth_rpc: str, start_block: int, end_block: int, batch_size: int = 100
    ):
        self.w3_op = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(op_rpc))
        self.w3_eth = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(eth_rpc))

        self.contract = self.w3_op.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)
        self.start_block = start_block
        self.end_block = end_block
        self.batch_size = batch_size
        self.results: Dict[int, Dict] = {}
        self.results_lock = Lock()

    async def get_l1_block(self, block_number: int) -> Tuple[str, int]:
        """Get L1 block data from optimism contract"""
        try:
            result = await self.contract.functions.l1_blocks(block_number).call()
            return result[0].hex(), result[1]
        except Exception:
            await asyncio.sleep(1)  # Basic backoff
            return await self.get_l1_block(block_number)

    async def process_block(self, block_number: int):
        """Process a single block"""
        try:
            l1_hash, l1_timestamp = await self.get_l1_block(block_number)
            eth_block = await self.w3_eth.eth.get_block(block_number)

            eth_hash = eth_block["hash"].hex()
            eth_timestamp = eth_block["timestamp"]

            with self.results_lock:
                self.results[block_number] = {
                    "l1_hash": l1_hash,
                    "eth_hash": eth_hash,
                    "l1_timestamp": l1_timestamp,
                    "eth_timestamp": eth_timestamp,
                    "hash_match": l1_hash == eth_hash,
                    "timestamp_match": l1_timestamp == eth_timestamp,
                }

        except Exception as e:
            logging.error(f"Error processing block {block_number}: {str(e)}")
            with self.results_lock:
                self.results[block_number] = {"error": str(e)}

    def save_results(self):
        """Save current results to file"""
        filename = "scan_results.json"
        with self.results_lock:
            with open(filename, "w") as f:
                json.dump(self.results, f, indent=2)
        logging.info(f"Results saved to {filename}")

    async def scan_batch(self, start: int, end: int):
        """Scan a batch of blocks"""
        tasks = []
        for block_num in range(start, min(end, self.end_block)):
            tasks.append(self.process_block(block_num))
        await asyncio.gather(*tasks)

    async def scan_blocks(self):
        """Main scanning function"""
        for batch_start in range(self.start_block, self.end_block, self.batch_size):
            batch_end = min(batch_start + self.batch_size, self.end_block)
            logging.info(f"Scanning blocks {batch_start} to {batch_end}")

            await self.scan_batch(batch_start, batch_end)
            self.save_results()  # Save after each batch

            completed = batch_end - self.start_block
            total = self.end_block - self.start_block
            logging.info(f"Progress: {completed}/{total} blocks ({completed/total*100:.2f}%)")


async def main():
    scanner = BlockScanner(
        op_rpc="https://lb.drpc.org/ogrpc?network=optimism&dkey=" + DRPC_API_KEY,
        eth_rpc="https://lb.drpc.org/ogrpc?network=ethereum&dkey=" + DRPC_API_KEY,
        start_block=21666325,
        end_block=21671472,
        batch_size=100,
    )

    await scanner.scan_blocks()
    scanner.save_results()  # Final save

    # Print summary
    mismatches = sum(
        1 for r in scanner.results.values() if isinstance(r, dict) and not r.get("hash_match", True)
    )
    logging.info(f"Scan complete. Found {mismatches} mismatches")


if __name__ == "__main__":
    asyncio.run(main())
