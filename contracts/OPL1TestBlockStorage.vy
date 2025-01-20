# pragma version ~=0.4

"""
@title OP L1 Block Oracle with validation
@dev Purpose is to be deployed on testnet and spammed to verify OP stack behavior in case of reorgs
@notice Fetches and validates L1 block data against the oracle
"""

from interfaces import IL1Block

################################################################
#                           STORAGE                            #
################################################################

L1BLOCK_ORACLE: immutable(IL1Block)

l1_blocks: public(HashMap[uint64, Block])
last_fetched_block: public(uint64)

struct Block:
    block_hash: bytes32
    block_timestamp: uint64

event BlockMismatch:
    block_number: uint64
    stored_hash: bytes32
    oracle_hash: bytes32
    stored_timestamp: uint64
    oracle_timestamp: uint64

################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__(l1block_precompile_address: address):
    L1BLOCK_ORACLE = IL1Block(l1block_precompile_address)
    self._fetch_latest_block()

################################################################
#                        INTERNAL FUNCTIONS                    #
################################################################

@internal
def _fetch_latest_block():
    block_number: uint64 = staticcall L1BLOCK_ORACLE.number()
    oracle_hash: bytes32 = staticcall L1BLOCK_ORACLE.hash()
    oracle_timestamp: uint64 = staticcall L1BLOCK_ORACLE.timestamp()

    if self._is_fetched(block_number):
        stored: Block = self.l1_blocks[block_number]
        if stored.block_hash != oracle_hash or stored.block_timestamp != oracle_timestamp:
            log BlockMismatch(
                block_number,
                stored.block_hash,
                oracle_hash,
                stored.block_timestamp,
                oracle_timestamp
            )
            # We keep the first seen values and don't update
    else:
        # Store new block data
        self.l1_blocks[block_number] = Block(
            block_hash=oracle_hash,
            block_timestamp=oracle_timestamp
        )
        self.last_fetched_block = block_number

@internal
def _is_fetched(block_number: uint64) -> bool:
    return self.l1_blocks[block_number].block_hash != empty(bytes32)

################################################################
#                      EXTERNAL FUNCTIONS                      #
################################################################

@external
def fetch_latest_block():
    self._fetch_latest_block()

@external
def get_block_hash(block_number: uint64) -> bytes32:
    block_hash: bytes32 = self.l1_blocks[block_number].block_hash
    assert block_hash != empty(bytes32), "Block not fetched"
    return block_hash

@external
def get_block_timestamp(block_number: uint64) -> uint64:
    block_timestamp: uint64 = self.l1_blocks[block_number].block_timestamp
    assert block_timestamp != 0, "Block not fetched"
    return block_timestamp

@external
@view
def peek_l1block_number() -> uint64:
    return staticcall L1BLOCK_ORACLE.number()
