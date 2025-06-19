"""
Shared fixtures and utilities for fuzzing tests
"""

import pytest
import boa
from eth_utils import keccak
import rlp
import os
from web3 import Web3


@pytest.fixture(scope="session")
def decoder():
    """Deploy the BlockHeaderRLPDecoder contract"""
    deployer = boa.env.generate_address()
    with boa.env.prank(deployer):
        return boa.load("contracts/modules/BlockHeaderRLPDecoder.vy")


@pytest.fixture(scope="session")
def eth_rpc_url():
    """Get Ethereum RPC URL with fallback to public endpoints"""
    api_key = os.getenv("DRPC_API_KEY")

    if api_key:
        return f"https://lb.drpc.org/ogrpc?network=ethereum&dkey={api_key}"

    # Try public RPCs in order of preference
    public_rpcs = [
        "https://eth.llamarpc.com",
        "https://ethereum.publicnode.com",
        "https://eth.drpc.org",
        "https://rpc.payload.de",
        "https://1rpc.io/eth",
    ]

    # Test which public RPC is working
    for rpc_url in public_rpcs:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
            # Try to get the latest block number as a test
            w3.eth.block_number
            print(f"Using public RPC: {rpc_url}")
            return rpc_url
        except Exception:
            continue

    # If all fail, return the first one and let tests handle the error
    print("Warning: No working RPC found, tests may fail")
    return public_rpcs[0]


@pytest.fixture(scope="session")
def eth_web3_client(eth_rpc_url):
    """Web3 client for fetching mainnet blocks"""
    return Web3(Web3.HTTPProvider(eth_rpc_url))


class HeaderFactory:
    """Factory for creating valid Ethereum block headers for different eras"""

    @staticmethod
    def create_pre_eip1559_header(
        block_number: int = 12964999, timestamp: int = 1627503271, extra_data: bytes = b"test"
    ) -> bytes:
        """Create a valid pre-EIP-1559 header (15 fields)"""
        fields = [
            keccak(f"parent_{block_number}".encode()),
            keccak(b""),
            b"\x42" * 20,
            keccak(f"state_{block_number}".encode()),
            keccak(b""),
            keccak(f"receipts_{block_number}".encode()),
            b"\x00" * 256,
            10000000000000000,
            block_number,
            30000000,
            29999832,
            timestamp,
            extra_data,
            b"\x00" * 32,
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf0",
        ]
        return rlp.encode(fields)

    @staticmethod
    def create_eip1559_header(
        block_number: int = 12965000, timestamp: int = 1628166812, base_fee: int = 1000000000
    ) -> bytes:
        """Create a valid EIP-1559 header (16 fields)"""
        fields = [
            keccak(f"parent_{block_number}".encode()),
            keccak(b""),
            b"\x42" * 20,
            keccak(f"state_{block_number}".encode()),
            keccak(b""),
            keccak(f"receipts_{block_number}".encode()),
            b"\x00" * 256,
            10000000000000000,
            block_number,
            30000000,
            20000000,
            timestamp,
            b"eip1559",
            b"\x00" * 32,
            b"\x00" * 8,
            base_fee,
        ]
        return rlp.encode(fields)

    @staticmethod
    def create_post_merge_header(
        block_number: int = 15537394, timestamp: int = 1663224174
    ) -> bytes:
        """Create a valid post-merge (PoS) header"""
        fields = [
            keccak(f"parent_{block_number}".encode()),
            keccak(b""),
            b"\x42" * 20,
            keccak(f"state_{block_number}".encode()),
            keccak(b""),
            keccak(f"receipts_{block_number}".encode()),
            b"\x00" * 256,
            0,  # PoS difficulty
            block_number,
            30000000,
            15000000,
            timestamp,
            b"",
            b"\x00" * 32,
            b"\x00" * 8,
            10574710144,
        ]
        return rlp.encode(fields)

    @staticmethod
    def create_shanghai_header(block_number: int = 17034870, timestamp: int = 1681338455) -> bytes:
        """Create a valid Shanghai header (17 fields with withdrawals)"""
        fields = [
            keccak(f"parent_{block_number}".encode()),
            keccak(b""),
            b"\x42" * 20,
            keccak(f"state_{block_number}".encode()),
            keccak(b""),
            keccak(f"receipts_{block_number}".encode()),
            b"\x00" * 256,
            0,
            block_number,
            30000000,
            15000000,
            timestamp,
            b"",
            b"\x00" * 32,
            b"\x00" * 8,
            7819184211,
            keccak(b"withdrawals"),  # withdrawals_root
        ]
        return rlp.encode(fields)

    @staticmethod
    def create_cancun_header(block_number: int = 19426587, timestamp: int = 1710338135) -> bytes:
        """Create a valid Cancun header (20 fields with blob gas)"""
        fields = [
            keccak(f"parent_{block_number}".encode()),
            keccak(b""),
            b"\x42" * 20,
            keccak(f"state_{block_number}".encode()),
            keccak(b""),
            keccak(f"receipts_{block_number}".encode()),
            b"\x00" * 256,
            0,
            block_number,
            30000000,
            15000000,
            timestamp,
            b"",
            b"\x00" * 32,
            b"\x00" * 8,
            78854037915,
            keccak(b"withdrawals"),
            131072,  # blob_gas_used
            0,  # excess_blob_gas
            keccak(b"beacon"),  # parent_beacon_block_root
        ]
        return rlp.encode(fields)

    @staticmethod
    def create_header_for_block(block_number: int) -> bytes:
        """Create appropriate header based on block number"""
        if block_number < 12965000:
            return HeaderFactory.create_pre_eip1559_header(block_number)
        elif block_number < 15537393:
            return HeaderFactory.create_eip1559_header(block_number)
        elif block_number < 17034870:
            return HeaderFactory.create_post_merge_header(block_number)
        elif block_number < 19426587:
            return HeaderFactory.create_shanghai_header(block_number)
        else:
            return HeaderFactory.create_cancun_header(block_number)


class AttackVectorFactory:
    """Factory for creating malicious headers with various attack vectors"""

    @staticmethod
    def create_truncated_header(valid_header: bytes, truncate_at: float = 0.5) -> bytes:
        """Create a truncated header"""
        return valid_header[: int(len(valid_header) * truncate_at)]

    @staticmethod
    def create_wrong_field_size_header(field_index: int, wrong_size: int) -> bytes:
        """Create header with wrong field size"""
        fields = [
            b"\x00" * 32,  # parent_hash
            b"\x00" * 32,  # uncles_hash
            b"\x00" * 20,  # coinbase
            b"\x00" * 32,  # state_root
            b"\x00" * 32,  # tx_root
            b"\x00" * 32,  # receipt_root
            b"\x00" * 256,  # bloom
            0,
            0,
            5000,
            0,
            0,
            b"",
            b"\x00" * 32,
            b"\x00" * 8,
        ]

        # Corrupt specific field
        if field_index == 0:  # parent_hash
            fields[0] = b"\x00" * wrong_size
        elif field_index == 2:  # coinbase
            fields[2] = b"\x00" * wrong_size
        elif field_index == 3:  # state_root
            fields[3] = b"\x00" * wrong_size

        return rlp.encode(fields)

    @staticmethod
    def create_type_confusion_header() -> bytes:
        """Create header with wrong types (lists instead of bytes)"""
        fields = [
            [b"list", b"not", b"bytes"],  # parent_hash should be bytes
            b"\x00" * 32,
            b"\x00" * 20,
            b"\x00" * 32,
            b"\x00" * 32,
            b"\x00" * 32,
            b"\x00" * 256,
            0,
            0,
            5000,
            0,
            0,
            b"",
            b"\x00" * 32,
            b"\x00" * 8,
        ]
        return rlp.encode(fields)

    @staticmethod
    def create_deeply_nested_rlp(depth: int = 10) -> bytes:
        """Create deeply nested RLP structure"""
        data = b"test"
        for _ in range(depth):
            data = rlp.encode([data])
        return data

    @staticmethod
    def create_overflow_length_header() -> bytes:
        """Create header with overflow length indicators"""
        # Start with long list indicator claiming huge payload
        data = bytearray([0xF8, 0xFF])  # Claims 255 byte payload
        # Add some valid data (but not 255 bytes)
        data.extend(b"\x00" * 100)
        return bytes(data)


# Real mainnet block data (fetched from eth.llamarpc.com)
MAINNET_BLOCKS = {
    # Genesis block (block 0)
    0: {
        "rlp_hex": "f90214a00000000000000000000000000000000000000000000000000000000000000000a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347940000000000000000000000000000000000000000a0d7f8974fb5ac78d9ac099b9ad5018bedc2ce0a72dad1827a1709da30580f0544a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421b9010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000850400000000808213888080a011bbe8db4e347b4e8c937c1c8370e4b5ed33adb3db69cbdb7a38e1e50b1b82faa00000000000000000000000000000000000000000000000000000000000000000880000000000000042",
        "block_hash": "0xd4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",
        "parent_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "state_root": "0xd7f8974fb5ac78d9ac099b9ad5018bedc2ce0a72dad1827a1709da30580f0544",
        "number": 0,
        "timestamp": 0,
    },
    # London fork block (EIP-1559)
    12965000: {
        "rlp_hex": "f9021fa03de6bb3849a138e6ab0b83a3a00dc7433f1e83f7fd488e4bba78f2fe2631a633a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347947777788200b672a42421017f65ede4fc759564c8a041cf6e8e60fd087d2b00360dc29e5bfb21959bce1f4c242fd1ad7c4da968eb87a0dfcb68d3a3c41096f4a77569db7956e0a0e750fad185948e54789ea0e51779cba08a8865cd785e2e9dfce7da83aca010b10b9af2abbd367114b236f149534c821db9010024e74ad77d9a2b27bdb8f6d6f7f1cffdd8cfb47fdebd433f011f7dfcfbb7db638fadd5ff66ed134ede2879ce61149797fbcdf7b74f6b7de153ec61bdaffeeb7b59c3ed771a2fe9eaed8ac70e335e63ff2bfe239eaff8f94ca642fdf7ee5537965be99a440f53d2ce057dbf9932be9a7b9a82ffdffe4eeee1a66c4cfb99fe4540fbff936f97dde9f6bfd9f8cefda2fc174d23dfdb7d6f7dfef5f754fe6a7eec92efdbff779b5feff3beafebd7fd6e973afebe4f5d86f3aafb1f73bf1e1d0cdd796d89827edeffe8fb6ae6d7bf639ec5f5ff4c32f31f6b525b676c7cdf5e5c75bfd5b7bd1928b6f43aac7fa0f6336576e5f7b7dfb9e8ebbe6f6efe2f9dfe8b3f56871b81c1fe05b21883c5d4888401ca35428401ca262984610bdaa69768747470733a2f2f7777772e6b7279707465782e6f7267a09620b46a81a4795cf4449d48e3270419f58b09293a5421205f88179b563f815a88b223da049adf2216843b9aca00",
        "block_hash": "0x9b83c12c69edb74f6c8dd5d052765c1adf940e320bd1291696e6fa07829eee71",
        "parent_hash": "0x3de6bb3849a138e6ab0b83a3a00dc7433f1e83f7fd488e4bba78f2fe2631a633",
        "state_root": "0x41cf6e8e60fd087d2b00360dc29e5bfb21959bce1f4c242fd1ad7c4da968eb87",
        "number": 12965000,
        "timestamp": 1628166822,
        "base_fee_per_gas": 1000000000,
    },
    # The Merge block (transition to PoS)
    15537393: {
        "rlp_hex": "f9021ba02b3ea3cd4befcab070812443affb08bf17a91ce382c714a536ca3cacab82278ba01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d4934794829bd824b016326a401d083b33d092293333a830a04919dafa6ac8becfbbd0c2808f6c9511a057c21e42839caff5dfb6d3ef514951a0dd5eec02b019ff76e359b09bfa19395a2a0e97bc01e70d8d5491e640167c96a8a0baa842cfd552321a9c2450576126311e071680a1258032219c6490b663c1dab8b90100000004000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000080000000000000000000000000000000000000000000000000200000000000000000008000000000040000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000084000000000010020000000000000000000000000000000000020000000200000000200000000000000000000000000000000000000000400000000000000000000000008727472e1db3626a83ed14f18401c9c3808401c9a205846322c96292e4b883e5bda9e7a59ee4bb99e9b1bc460021a04cbec03dddd4b939730a7fe6048729604d4266e82426d472a2b2024f3cc4043f8862a3ee77461d4fc9850a1a4e5f06",
        "block_hash": "0x55b11b918355b1ef9c5db810302ebad0bf2544255b530cdce90674d5887bb286",
        "parent_hash": "0x2b3ea3cd4befcab070812443affb08bf17a91ce382c714a536ca3cacab82278b",
        "state_root": "0x4919dafa6ac8becfbbd0c2808f6c9511a057c21e42839caff5dfb6d3ef514951",
        "number": 15537393,
        "timestamp": 1663224162,
        "difficulty": 11055787484078698,
        "base_fee_per_gas": 43391016710,
    },
    # Shanghai fork block (withdrawals)
    17034870: {
        "rlp_hex": "f9023da0c2558f8143d5f5acb8382b8cb2b8e2f1a10c8bdfeededad850eaca048ed85d8fa01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d4934794388c818ca8b9251b393131c08a736a67ccb19297a07fd42f5027bc18315b3781e65f19e4c8828fd5c5fce33410f0fb4fea0b65541fa06f235d618461c08943aa5c23cc751310d6177ab8a9b9a7b66ffa637d988680e6a0e0ac34bafdd757bcca2dea27a3fc5870dd0836998877e29361c1fc55e19416ecb90100b06769bc11f4d7a51a3bc4bed59367b75c32d1bd79e5970e73732ac0eed0251af0e2abc8811fc1b4c5d45a4a4eb5c5af9e73cc9a8be6ace72faadc03536d6b69fcdf80116fd89f7efbdbf38ff957e8f6ae83ccac60cf4b7c8b1c9487bebfa8ed6e42297e17172d5b678dd3f283b22f49bbf4a0565eb93d9d797b2f9a0adaff9813af53d6fffa71d5a6fb056ab73ca87659dc97c19f99839c6c3138e527161b4dfee8b1f64d42f927abc745f3ff168e8e9510e2e079f4868ba8ff94faf37c9a7947a43c1b4c931dfbef88edeb2d7ede5ceaebc85095cfbbd206646def0138683b687fa63fdf22898260d616bc714d698bc5748c7a5bff0a4a32dd797596a794a080840103ee768401c9c3808401c9bfe2846437306f99d883010b05846765746888676f312e32302e32856c696e7578a0812ed704cc408c435c7baa6e86296c1ac654a139ae8c4a26d6460742b951d4f988000000000000000085042fbae6d5a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421",
        "block_hash": "0xe22c56f211f03baadcc91e4eb9a24344e6848c5df4473988f893b58223f5216c",
        "parent_hash": "0xc2558f8143d5f5acb8382b8cb2b8e2f1a10c8bdfeededad850eaca048ed85d8f",
        "state_root": "0x7fd42f5027bc18315b3781e65f19e4c8828fd5c5fce33410f0fb4fea0b65541f",
        "number": 17034870,
        "timestamp": 1681338479,
        "withdrawals_root": "0x56e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421",
        "base_fee_per_gas": 17980647125,
    },
    # Cancun fork block (blob gas)
    19426587: {
        "rlp_hex": "f9025fa0db672c41cfd47c84ddb478ffde5a09b76964f77dceca0e62bdf719c965d73e7fa01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d4934794dae56d85ff707b3d19427f23d8b03b7b76da1006a0bd33ab68095087d81beb810b3f5d0b16050b3f798ae3978e440bab048dd78992a020cbdd2cd6113eb72dade6be7ec18fe6a7167a8a0af912a2171af909a8cda9f6a059c3691e83e0ddeafeedd07f5e30850cc6c963e85327aa1201fbe1f731ff3dbcb901000021000000000001080801008000320000000060000000000005000080c200040000100000006002440409000000010402011000890200000a201000042800440442148c0100208408004009012000200000040801644808800000600029068004012001020000002510000000020900c8122010020284000080021006000101000000401810621c0040000000001010000004800100404808000640255000002201000010002000000040c0000000000400a004000c0000884000304e00202400100402000000004204000004041008005600001000001000000003015030120012280000022020910040429204408020009000000010120000400000000400808401286d1b8401c9c380832830cd8465f1b05799d883010d0e846765746888676f312e32312e37856c696e7578a02617b147c1b3cf43a28d08d508ab2d8860c6cf40da58837676cfaaf4f9e07f62880000000000000000850e6ca77a30a06c119891018ed3a43d04197a8eb94d85f287304b8ace21b08e9f68cbd2f8de618080a0b35bb80bc5f4e3d8f19b62f6274add24dca334db242546c3024403027aaf6412",
        "block_hash": "0xf8e2f40d98fe5862bc947c8c83d34799c50fb344d7445d020a8a946d891b62ee",
        "parent_hash": "0xdb672c41cfd47c84ddb478ffde5a09b76964f77dceca0e62bdf719c965d73e7f",
        "state_root": "0xbd33ab68095087d81beb810b3f5d0b16050b3f798ae3978e440bab048dd78992",
        "number": 19426587,
        "timestamp": 1710338135,
        "blob_gas_used": 131072,
        "excess_blob_gas": 0,
        "parent_beacon_block_root": "0xb35bb80bc5f4e3d8f19b62f6274add24dca334db242546c3024403027aaf6412",
        "base_fee_per_gas": 61952457264,
    },
}
