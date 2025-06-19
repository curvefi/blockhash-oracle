"""
Core validation tests for BlockHeaderRLPDecoder

Tests valid header decoding, differential fuzzing, and mainnet validation.
"""

import pytest
from hypothesis import given, strategies as st, settings
from eth_utils import keccak
import rlp
from typing import Dict, Any

from conftest import HeaderFactory, MAINNET_BLOCKS


class ReferenceDecoder:
    """Reference decoder using rlp.decode for differential testing"""

    @staticmethod
    def decode_header(encoded_header: bytes) -> Dict[str, Any]:
        """Decode header using rlp.decode and extract fields"""
        try:
            decoded = rlp.decode(encoded_header)

            if not isinstance(decoded, list) or len(decoded) < 15:
                raise ValueError("Invalid header structure")

            # Validate field sizes
            if len(decoded[0]) != 32:  # parent_hash
                raise ValueError("Parent hash must be 32 bytes")
            if len(decoded[2]) != 20:  # coinbase
                raise ValueError("Coinbase must be 20 bytes")
            if len(decoded[3]) != 32:  # state_root
                raise ValueError("State root must be 32 bytes")
            if len(decoded[5]) != 32:  # receipt_root
                raise ValueError("Receipt root must be 32 bytes")

            return {
                "parent_hash": decoded[0],
                "state_root": decoded[3],
                "receipt_root": decoded[5],
                "block_number": int.from_bytes(decoded[8], "big") if decoded[8] else 0,
                "timestamp": int.from_bytes(decoded[11], "big") if decoded[11] else 0,
                "block_hash": keccak(encoded_header),
            }
        except Exception as e:
            raise ValueError(f"Failed to decode: {str(e)}")


class TestValidHeaders:
    """Test decoding of valid Ethereum headers across all eras"""

    def test_all_era_headers(self, decoder):
        """Test headers from each Ethereum era"""
        test_cases = [
            ("Pre-EIP-1559", HeaderFactory.create_pre_eip1559_header()),
            ("EIP-1559", HeaderFactory.create_eip1559_header()),
            ("Post-Merge", HeaderFactory.create_post_merge_header()),
            ("Shanghai", HeaderFactory.create_shanghai_header()),
            ("Cancun", HeaderFactory.create_cancun_header()),
        ]

        for era_name, header in test_cases:
            result = decoder.decode_block_header(header)

            # Verify basic properties
            assert result.block_hash == keccak(header)
            assert isinstance(result.block_number, int)
            assert isinstance(result.timestamp, int)
            assert len(result.parent_hash) == 32
            assert len(result.state_root) == 32
            assert len(result.receipt_root) == 32

            print(f"✓ {era_name} header decoded successfully")

    @given(
        block_number=st.integers(min_value=0, max_value=25000000),
        timestamp=st.integers(min_value=0, max_value=2**32 - 1),
        gas_limit=st.integers(min_value=5000, max_value=50000000),
    )
    @settings(max_examples=100, deadline=None)
    def test_header_consistency(self, decoder, block_number, timestamp, gas_limit):
        """Test that headers decode consistently"""
        # Create header for given block
        header = HeaderFactory.create_header_for_block(block_number)

        # Decode multiple times
        results = []
        for _ in range(3):
            result = decoder.decode_block_header(header)
            results.append(result)

        # All results should be identical
        for i in range(1, len(results)):
            assert results[i].block_hash == results[0].block_hash
            assert results[i].parent_hash == results[0].parent_hash
            assert results[i].state_root == results[0].state_root
            assert results[i].block_number == results[0].block_number
            assert results[i].timestamp == results[0].timestamp


class TestDifferentialFuzzing:
    """Test contract against rlp.decode reference implementation"""

    @given(
        parent_hash=st.binary(min_size=32, max_size=32),
        state_root=st.binary(min_size=32, max_size=32),
        receipt_root=st.binary(min_size=32, max_size=32),
        block_number=st.integers(min_value=0, max_value=2**64 - 1),
        timestamp=st.integers(min_value=0, max_value=2**64 - 1),
        gas_limit=st.integers(min_value=5000, max_value=2**64 - 1),
        gas_used=st.integers(min_value=0, max_value=2**64 - 1),
        extra_data_size=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=200, deadline=None)
    def test_valid_headers_match_reference(
        self,
        decoder,
        parent_hash,
        state_root,
        receipt_root,
        block_number,
        timestamp,
        gas_limit,
        gas_used,
        extra_data_size,
    ):
        """Valid headers should decode identically to reference"""
        gas_used = min(gas_used, gas_limit)

        fields = [
            parent_hash,
            keccak(b"uncles"),
            b"\x42" * 20,
            state_root,
            keccak(b"txs"),
            receipt_root,
            b"\x00" * 256,
            0,
            block_number,
            gas_limit,
            gas_used,
            timestamp,
            b"test" * (extra_data_size // 4),
            keccak(b"mix"),
            b"\x00" * 8,
        ]

        if block_number >= 12965000:
            fields.append(1000000000)

        encoded = rlp.encode(fields)

        # Decode with both
        ref_result = ReferenceDecoder.decode_header(encoded)
        contract_result = decoder.decode_block_header(encoded)

        # Compare critical fields
        assert contract_result.block_hash == ref_result["block_hash"]
        assert contract_result.parent_hash == ref_result["parent_hash"]
        assert contract_result.state_root == ref_result["state_root"]
        assert contract_result.receipt_root == ref_result["receipt_root"]
        assert contract_result.block_number == ref_result["block_number"]
        assert contract_result.timestamp == ref_result["timestamp"]

    def test_contract_never_more_permissive(self, decoder):
        """Contract should never accept headers that rlp.decode rejects"""
        invalid_headers = [
            # Empty list
            rlp.encode([]),
            # Too few fields
            rlp.encode([b"\x00" * 32] * 10),
            # Wrong field types
            rlp.encode([[b"nested"], b"\x00" * 32] + [b"\x00" * 32] * 13),
            # Wrong field sizes
            rlp.encode([b"\x00" * 31] + [b"\x00" * 32] * 14),  # Short parent_hash
            # Not a list
            rlp.encode(b"not a list"),
        ]

        for encoded in invalid_headers:
            ref_accepted = False
            contract_accepted = False

            try:
                ReferenceDecoder.decode_header(encoded)
                ref_accepted = True
            except Exception:
                pass

            try:
                decoder.decode_block_header(encoded)
                contract_accepted = True
            except Exception:
                pass

            # Contract should not be more permissive
            if not ref_accepted and contract_accepted:
                pytest.fail("Contract accepted invalid header that reference rejected")


class TestMainnetValidation:
    """Validate against real mainnet blocks"""

    def test_all_mainnet_blocks(self, decoder):
        """Test all mainnet blocks decode correctly"""
        for block_num, block_data in sorted(MAINNET_BLOCKS.items()):
            encoded = bytes.fromhex(
                block_data["rlp_hex"][2:]
                if block_data["rlp_hex"].startswith("0x")
                else block_data["rlp_hex"]
            )

            result = decoder.decode_block_header(encoded)

            # Verify critical fields
            assert result.block_number == block_num
            assert result.timestamp == block_data["timestamp"]
            assert result.block_hash == bytes.fromhex(block_data["block_hash"][2:])

            if block_num > 0:
                assert result.parent_hash == bytes.fromhex(block_data["parent_hash"][2:])

            assert result.state_root == bytes.fromhex(block_data["state_root"][2:])

            print(f"✓ Block {block_num:>10}: Validated")

    def test_block_hash_computation(self, decoder):
        """Verify block hash computation matches Ethereum"""
        for block_num, block_data in MAINNET_BLOCKS.items():
            encoded = bytes.fromhex(
                block_data["rlp_hex"][2:]
                if block_data["rlp_hex"].startswith("0x")
                else block_data["rlp_hex"]
            )

            # Compute hash and compare
            computed_hash = keccak(encoded)
            expected_hash = bytes.fromhex(block_data["block_hash"][2:])

            assert computed_hash == expected_hash

            # Verify decoder returns same hash
            result = decoder.decode_block_header(encoded)
            assert result.block_hash == expected_hash

    @pytest.mark.parametrize("block_num", sorted(MAINNET_BLOCKS.keys()))
    def test_individual_mainnet_block(self, decoder, block_num):
        """Parameterized test for each mainnet block"""
        block_data = MAINNET_BLOCKS[block_num]
        encoded = bytes.fromhex(
            block_data["rlp_hex"][2:]
            if block_data["rlp_hex"].startswith("0x")
            else block_data["rlp_hex"]
        )

        result = decoder.decode_block_header(encoded)

        assert result.block_number == block_num
        assert result.timestamp == block_data["timestamp"]
        assert result.block_hash == bytes.fromhex(block_data["block_hash"][2:])


class TestHeaderDeterminism:
    """Test that decoding is deterministic"""

    @given(
        block_number=st.integers(min_value=10000000, max_value=20000000),
        extra_data=st.binary(min_size=0, max_size=32),
    )
    @settings(max_examples=50, deadline=None)
    def test_encoding_decoding_determinism(self, decoder, block_number, extra_data):
        """Same input should always produce same output"""
        # Create header
        fields = [
            keccak(f"parent_{block_number}".encode()),
            keccak(b"uncles"),
            b"\x42" * 20,
            keccak(f"state_{block_number}".encode()),
            keccak(b"txs"),
            keccak(f"receipts_{block_number}".encode()),
            b"\x00" * 256,
            0,
            block_number,
            30000000,
            15000000,
            1700000000,
            extra_data,
            b"\x00" * 32,
            b"\x00" * 8,
        ]

        if block_number >= 12965000:
            fields.append(1000000000)

        # Encode once
        encoded1 = rlp.encode(fields)
        encoded2 = rlp.encode(fields)

        # Should be identical
        assert encoded1 == encoded2

        # Decode multiple times
        result1 = decoder.decode_block_header(encoded1)
        result2 = decoder.decode_block_header(encoded1)
        result3 = decoder.decode_block_header(encoded2)

        # All results should be identical
        assert result1.block_hash == result2.block_hash == result3.block_hash
        assert result1.block_number == result2.block_number == result3.block_number


class TestRandomMainnetBlocks:
    """Test with random mainnet blocks fetched via RPC"""

    def test_random_mainnet_blocks(self, decoder, eth_web3_client):
        """Fetch and validate 10 random mainnet block headers"""
        import random

        # Get current block number
        latest_block = eth_web3_client.eth.block_number

        # Select 10 random blocks from different eras
        # Ensure we test different fork rules
        block_ranges = [
            (1, 12964999),  # Pre-EIP-1559
            (12965000, 15537392),  # EIP-1559
            (15537393, 17034869),  # Post-merge (PoS)
            (17034870, 19426586),  # Shanghai
            (19426587, latest_block),  # Cancun
        ]

        selected_blocks = []

        # Get 2 blocks from each era
        for start, end in block_ranges:
            if start <= end and end <= latest_block:
                for _ in range(2):
                    block_num = random.randint(start, min(end, latest_block))
                    selected_blocks.append(block_num)

        print(f"\nTesting {len(selected_blocks)} random mainnet blocks:")

        for block_num in selected_blocks:
            # Fetch block from RPC
            block_data = eth_web3_client.eth.get_block(block_num, full_transactions=False)

            # Encode the header
            encoded_header = self._encode_block_header(block_data)

            # Decode with our contract
            result = decoder.decode_block_header(encoded_header)

            # Verify critical fields
            assert result.block_number == block_data["number"]
            assert result.timestamp == block_data["timestamp"]
            assert result.parent_hash == bytes(block_data["parentHash"])
            assert result.state_root == bytes(block_data["stateRoot"])
            assert result.receipt_root == bytes(block_data["receiptsRoot"])

            # Verify block hash
            expected_hash = bytes(block_data["hash"])
            computed_hash = keccak(encoded_header)
            assert computed_hash == expected_hash, f"Block {block_num}: Hash mismatch"
            assert result.block_hash == expected_hash

            print(f"✓ Block {block_num}: Validated successfully")

    def test_recent_blocks_sequence(self, decoder, eth_web3_client):
        """Test a sequence of recent blocks to verify parent relationships"""
        latest_block = eth_web3_client.eth.block_number

        # Get 5 consecutive recent blocks
        start_block = latest_block - 10
        blocks_to_test = 5

        print(f"\nTesting sequence of {blocks_to_test} recent blocks starting from {start_block}:")

        previous_hash = None

        for i in range(blocks_to_test):
            block_num = start_block + i
            block_data = eth_web3_client.eth.get_block(block_num, full_transactions=False)

            # Encode and decode
            encoded_header = self._encode_block_header(block_data)
            result = decoder.decode_block_header(encoded_header)

            # Verify block
            assert result.block_number == block_num

            # Compute expected hash from encoded header
            expected_hash = keccak(encoded_header)
            assert (
                result.block_hash == expected_hash
            ), f"Block {block_num}: Hash mismatch! Expected: {expected_hash.hex()}, Got: {result.block_hash.hex()}"

            # Also verify it matches the RPC-provided hash
            assert expected_hash == bytes(
                block_data["hash"]
            ), f"Block {block_num}: Our encoding doesn't match RPC hash!"

            # Verify parent relationship
            if previous_hash:
                assert result.parent_hash == previous_hash

            previous_hash = result.block_hash

            print(f"✓ Block {block_num}: Parent chain verified")

    def test_block_hash_validation(self, decoder, eth_web3_client):
        """Specifically test block hash computation for 10 random blocks"""
        import random

        # Get current block number
        latest_block = eth_web3_client.eth.block_number

        # Select 10 random blocks across full history
        selected_blocks = []
        for _ in range(10):
            # Random block from genesis to current
            block_num = random.randint(1, latest_block)
            selected_blocks.append(block_num)

        print("\nValidating block hashes for 10 random blocks:")

        for block_num in selected_blocks:
            # Fetch block
            block_data = eth_web3_client.eth.get_block(block_num, full_transactions=False)

            # Encode header
            encoded_header = self._encode_block_header(block_data)

            # The critical test: Does keccak(encoded_header) == block_hash?
            expected_hash = bytes(block_data["hash"])
            computed_hash = keccak(encoded_header)

            # First verify our encoding is correct
            assert computed_hash == expected_hash, (
                f"Block {block_num}: Our encoding produces wrong hash! "
                f"Expected: {expected_hash.hex()}, Got: {computed_hash.hex()}"
            )

            # Now verify the decoder returns the same hash
            result = decoder.decode_block_header(encoded_header)
            assert result.block_hash == expected_hash, (
                f"Block {block_num}: Decoder returned wrong hash! "
                f"Expected: {expected_hash.hex()}, Got: {result.block_hash.hex()}"
            )

            # Also verify block number as sanity check
            assert result.block_number == block_num

            # Determine era for logging
            if block_num < 12965000:
                era = "Pre-EIP-1559"
            elif block_num < 15537393:
                era = "EIP-1559"
            elif block_num < 17034870:
                era = "Post-Merge"
            elif block_num < 19426587:
                era = "Shanghai"
            else:
                era = "Cancun"

            print(f"✓ Block {block_num} ({era}): Hash validated - {expected_hash.hex()[:16]}...")

    def _encode_block_header(self, block_data: Dict) -> bytes:
        """Encode a block header from web3 block data"""

        def ensure_bytes(value):
            # Handle HexBytes objects from Web3
            if hasattr(value, "hex"):
                # This is a HexBytes object
                return bytes(value)
            if isinstance(value, bytes):
                return value
            if isinstance(value, str):
                hex_str = value[2:] if value.startswith("0x") else value
                return bytes.fromhex(hex_str)
            return value

        fields = [
            ensure_bytes(block_data["parentHash"]),
            ensure_bytes(block_data["sha3Uncles"]),
            ensure_bytes(block_data["miner"]),
            ensure_bytes(block_data["stateRoot"]),
            ensure_bytes(block_data["transactionsRoot"]),
            ensure_bytes(block_data["receiptsRoot"]),
            ensure_bytes(block_data["logsBloom"]),
            block_data["difficulty"],
            block_data["number"],
            block_data["gasLimit"],
            block_data["gasUsed"],
            block_data["timestamp"],
            ensure_bytes(block_data["extraData"]),
            ensure_bytes(block_data["mixHash"]),
            ensure_bytes(block_data["nonce"]),
        ]

        # Add EIP-1559 and later fields if present
        if block_data.get("baseFeePerGas") is not None:
            fields.append(block_data["baseFeePerGas"])

        # Handle withdrawalsRoot more carefully - check if it's present and not empty
        withdrawals_root = block_data.get("withdrawalsRoot")
        if withdrawals_root is not None and withdrawals_root != "0x" and withdrawals_root != b"":
            fields.append(ensure_bytes(withdrawals_root))

        # Add blob gas fields for Cancun
        if block_data.get("blobGasUsed") is not None:
            fields.append(block_data["blobGasUsed"])
        if block_data.get("excessBlobGas") is not None:
            fields.append(block_data["excessBlobGas"])

        # Handle parentBeaconBlockRoot
        parent_beacon = block_data.get("parentBeaconBlockRoot")
        if parent_beacon is not None and parent_beacon != "0x" and parent_beacon != b"":
            fields.append(ensure_bytes(parent_beacon))

        # Handle requestsHash (EIP-7685, added in recent blocks)
        requests_hash = block_data.get("requestsHash")
        if requests_hash is not None:
            fields.append(ensure_bytes(requests_hash))

        return rlp.encode(fields)
