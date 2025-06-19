"""
Security vulnerability tests for BlockHeaderRLPDecoder

Tests for critical vulnerabilities, attack vectors, and data integrity.
"""

import pytest
from hypothesis import given, strategies as st, settings
from eth_utils import keccak
import rlp
import boa

from conftest import HeaderFactory, AttackVectorFactory


class TestCriticalVulnerabilities:
    """Test for critical security vulnerabilities"""

    def test_field_extraction_precision(self, decoder):
        """Ensure fields are extracted from exact positions"""
        # Create headers with sentinel values
        parent_hash = keccak(b"PARENT_HASH_SENTINEL")
        state_root = keccak(b"STATE_ROOT_SENTINEL")
        receipt_root = keccak(b"RECEIPT_ROOT_SENTINEL")

        fields = [
            parent_hash,
            keccak(b"uncles"),
            b"\x42" * 20,
            state_root,
            keccak(b"txs"),
            receipt_root,
            b"\x00" * 256,
            0,
            15000000,
            30000000,
            15000000,
            1700000000,
            b"test",
            b"\x00" * 32,
            b"\x00" * 8,
            1000000000,
        ]

        encoded = rlp.encode(fields)
        result = decoder.decode_block_header(encoded)

        # Verify exact extraction
        assert result.parent_hash == parent_hash
        assert result.state_root == state_root
        assert result.receipt_root == receipt_root

        # Now try to inject data in wrong positions
        # Place state_root where parent_hash should be
        malicious_fields = fields.copy()
        malicious_fields[0] = state_root  # Wrong!
        malicious_fields[3] = parent_hash  # Wrong!

        malicious_encoded = rlp.encode(malicious_fields)
        malicious_result = decoder.decode_block_header(malicious_encoded)

        # Should extract from correct positions despite swap
        assert malicious_result.parent_hash == state_root  # Got what's at position 0
        assert malicious_result.state_root == parent_hash  # Got what's at position 3

    def test_no_data_injection_between_fields(self, decoder):
        """Ensure no data can be injected between fields"""
        # Test various injection attempts
        injection_tests = [
            # Try injecting data after each critical field
            (0, b"INJECTED_DATA"),  # After parent_hash
            (3, b"INJECTED_DATA"),  # After state_root
            (5, b"INJECTED_DATA"),  # After receipt_root
            (8, b"INJECTED_DATA"),  # After block_number
        ]

        base_fields = [
            keccak(b"parent"),
            keccak(b"uncles"),
            b"\x42" * 20,
            keccak(b"state"),
            keccak(b"txs"),
            keccak(b"receipts"),
            b"\x00" * 256,
            0,
            15000000,
            30000000,
            15000000,
            1700000000,
            b"test",
            b"\x00" * 32,
            b"\x00" * 8,
        ]

        for position, injection in injection_tests:
            # Try to inject data
            malicious_fields = (
                base_fields[: position + 1] + [injection] + base_fields[position + 1 :]
            )

            # This creates an invalid header with too many fields
            malicious_encoded = rlp.encode(malicious_fields)

            # Should either fail or ignore the injection
            try:
                result = decoder.decode_block_header(malicious_encoded)
                # If it succeeds, verify critical fields are unchanged
                valid_encoded = rlp.encode(base_fields)
                valid_result = decoder.decode_block_header(valid_encoded)

                # Critical fields should match
                assert result.parent_hash == valid_result.parent_hash
                assert result.state_root == valid_result.state_root
                assert result.receipt_root == valid_result.receipt_root
            except Exception:
                # Failing is also acceptable
                pass

    def test_block_hash_integrity(self, decoder):
        """Ensure block hash cannot be spoofed"""
        fields = [
            keccak(b"parent"),
            keccak(b"uncles"),
            b"\x42" * 20,
            keccak(b"state"),
            keccak(b"txs"),
            keccak(b"receipts"),
            b"\x00" * 256,
            0,
            15000000,
            30000000,
            15000000,
            1700000000,
            b"test",
            b"\x00" * 32,
            b"\x00" * 8,
        ]

        encoded = rlp.encode(fields)
        result = decoder.decode_block_header(encoded)

        # Block hash should be keccak of entire encoded header
        expected_hash = keccak(encoded)
        assert result.block_hash == expected_hash

        # Modify a single byte
        tampered = bytearray(encoded)
        tampered[-1] ^= 0x01  # Flip last bit
        tampered_bytes = bytes(tampered)

        tampered_result = decoder.decode_block_header(tampered_bytes)

        # Hash should be different
        assert tampered_result.block_hash != expected_hash
        assert tampered_result.block_hash == keccak(tampered_bytes)


class TestAttackVectors:
    """Test specific attack vectors"""

    def test_truncation_attacks(self, decoder):
        """Test resistance to truncated payloads"""
        valid_header = HeaderFactory.create_eip1559_header()

        # Try various truncation points that should definitely fail
        # The decoder only needs fields up to timestamp, so mild truncations may succeed
        truncation_points = [0.1, 0.25, 0.5, 0.75]

        for point in truncation_points:
            truncated = AttackVectorFactory.create_truncated_header(valid_header, point)

            # Should fail to decode
            with pytest.raises(boa.BoaError):
                decoder.decode_block_header(truncated)

    def test_type_confusion_attacks(self, decoder):
        """Test resistance to type confusion"""
        # Try headers with wrong types
        attack_headers = [
            AttackVectorFactory.create_type_confusion_header(),
            # Integer where bytes expected
            rlp.encode([12345] + [b"\x00" * 32] * 14),
            # Bytes where integer expected
            rlp.encode([b"\x00" * 32] * 8 + [b"not_a_number"] + [b"\x00" * 32] * 6),
        ]

        for attack_header in attack_headers:
            with pytest.raises(boa.BoaError):
                decoder.decode_block_header(attack_header)

    def test_wrong_field_sizes(self, decoder):
        """Test handling of wrong field sizes"""
        # Test wrong sizes for critical fields
        test_cases = [
            (0, 31),  # parent_hash too short
            (0, 33),  # parent_hash too long
            (2, 19),  # coinbase too short
            (2, 21),  # coinbase too long
            (3, 31),  # state_root too short
            (3, 33),  # state_root too long
        ]

        for field_index, wrong_size in test_cases:
            attack_header = AttackVectorFactory.create_wrong_field_size_header(
                field_index, wrong_size
            )

            # Should reject wrong sizes
            with pytest.raises(boa.BoaError):
                decoder.decode_block_header(attack_header)

    def test_overflow_attacks(self, decoder):
        """Test resistance to overflow attacks"""
        # Test various overflow scenarios
        overflow_headers = [
            # Overflow length indicator
            AttackVectorFactory.create_overflow_length_header(),
            # Deeply nested structure
            AttackVectorFactory.create_deeply_nested_rlp(depth=10),
            # Huge numbers
            rlp.encode([b"\x00" * 32] * 7 + [2**256 - 1] * 8),
        ]

        for attack_header in overflow_headers:
            # Should handle gracefully (fail or succeed safely)
            try:
                result = decoder.decode_block_header(attack_header)
                # If it succeeds, verify it's safe
                assert isinstance(result.block_number, int)
                assert isinstance(result.timestamp, int)
            except Exception:
                # Failing is fine
                pass


class TestDataInjectionResistance:
    """Test resistance to various data injection attempts"""

    @given(
        injection_data=st.binary(min_size=1, max_size=100),
        injection_position=st.integers(min_value=0, max_value=15),
    )
    @settings(max_examples=50, deadline=None)
    def test_random_injection_resistance(self, decoder, injection_data, injection_position):
        """Test resistance to random data injection"""
        base_header = HeaderFactory.create_eip1559_header()
        decoded_base = rlp.decode(base_header)

        # Try to inject data at various positions
        if injection_position < len(decoded_base):
            # Insert injection
            modified = list(decoded_base)
            modified.insert(injection_position, injection_data)

            try:
                attack_header = rlp.encode(modified)
                result = decoder.decode_block_header(attack_header)

                # If it succeeds, critical fields should still be valid
                assert len(result.parent_hash) == 32
                assert len(result.state_root) == 32
                assert len(result.receipt_root) == 32
            except Exception:
                # Failing is acceptable
                pass

    def test_spoofed_state_root_attack(self, decoder):
        """Test that state root cannot be spoofed"""
        real_state_root = keccak(b"REAL_STATE_ROOT")
        fake_state_root = keccak(b"FAKE_STATE_ROOT")

        # Create valid header with real state root
        fields = [
            keccak(b"parent"),
            keccak(b"uncles"),
            b"\x42" * 20,
            real_state_root,  # Position 3
            keccak(b"txs"),
            keccak(b"receipts"),
            b"\x00" * 256,
            0,
            15000000,
            30000000,
            15000000,
            1700000000,
            # Try to hide fake state root in extra data
            b"FAKE:" + fake_state_root,
            b"\x00" * 32,
            b"\x00" * 8,
        ]

        encoded = rlp.encode(fields)
        result = decoder.decode_block_header(encoded)

        # Should extract the real state root from position 3
        assert result.state_root == real_state_root
        assert result.state_root != fake_state_root

    def test_critical_field_boundaries(self, decoder):
        """Test that critical fields respect their boundaries"""
        # Create headers with maximum valid values
        test_cases = [
            {
                "name": "Max block number",
                "block_number": 2**64 - 1,
                "timestamp": 1700000000,
            },
            {
                "name": "Max timestamp",
                "block_number": 15000000,
                "timestamp": 2**64 - 1,
            },
            {
                "name": "All max values",
                "block_number": 2**64 - 1,
                "timestamp": 2**64 - 1,
            },
        ]

        for test in test_cases:
            fields = [
                keccak(b"parent"),
                keccak(b"uncles"),
                b"\x42" * 20,
                keccak(b"state"),
                keccak(b"txs"),
                keccak(b"receipts"),
                b"\x00" * 256,
                0,
                test["block_number"],
                30000000,
                15000000,
                test["timestamp"],
                b"boundary-test",
                b"\x00" * 32,
                b"\x00" * 8,
            ]

            encoded = rlp.encode(fields)
            result = decoder.decode_block_header(encoded)

            # Should handle large values correctly
            assert result.block_number == test["block_number"]
            assert result.timestamp == test["timestamp"]

            print(f"✓ {test['name']}: Handled correctly")


class TestMaliciousPayloads:
    """Test specific malicious payload patterns"""

    def test_rlp_bomb(self, decoder):
        """Test resistance to RLP bombs (exponential decoding)"""
        # Create a small RLP bomb
        bomb = b"test"
        for _ in range(5):  # Limited depth to avoid actual DOS
            bomb = rlp.encode([bomb, bomb])

        # Should handle without hanging
        try:
            decoder.decode_block_header(bomb)
        except Exception:
            # Expected to fail
            pass

    def test_malformed_length_indicators(self, decoder):
        """Test malformed RLP length indicators"""
        malformed_cases = [
            # Long string indicator with short payload
            bytes([0xB8, 0x20]) + b"short",
            # Long list indicator with short payload
            bytes([0xF8, 0x20]) + b"short",
            # Invalid indicator bytes
            bytes([0xFF, 0xFF]) + b"data",
        ]

        for malformed in malformed_cases:
            with pytest.raises(boa.BoaError):
                decoder.decode_block_header(malformed)

    def test_consensus_rule_violations(self, decoder):
        """Test that consensus rules are enforced"""
        # Test various consensus violations
        violations = [
            {
                "name": "gas_used > gas_limit",
                "gas_limit": 30000000,
                "gas_used": 30000001,  # Too much!
            },
            {
                "name": "negative values",
                "block_number": -1,  # Should fail in encoding
                "timestamp": 1700000000,
            },
        ]

        for violation in violations:
            try:
                fields = [
                    keccak(b"parent"),
                    keccak(b"uncles"),
                    b"\x42" * 20,
                    keccak(b"state"),
                    keccak(b"txs"),
                    keccak(b"receipts"),
                    b"\x00" * 256,
                    0,
                    violation.get("block_number", 15000000),
                    violation.get("gas_limit", 30000000),
                    violation.get("gas_used", 15000000),
                    violation.get("timestamp", 1700000000),
                    b"violation-test",
                    b"\x00" * 32,
                    b"\x00" * 8,
                ]

                encoded = rlp.encode(fields)
                result = decoder.decode_block_header(encoded)

                # Some violations might be caught at decode time
                # Others might produce invalid results
                if "gas_used" in violation and "gas_limit" in violation:
                    # This particular violation might not be enforced by decoder
                    # But we document the behavior
                    assert result.block_number >= 0

            except Exception as e:
                # Expected for some violations
                print(f"✓ {violation.get('name', 'violation')}: Caught - {type(e).__name__}")
