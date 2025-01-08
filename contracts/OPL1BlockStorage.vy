# pragma version ~=0.4

"""
@title L1 Block Oracle

@notice A contract for fetching and storing L1 block data including block hash,
timestamp, and block number. Fetches data from an L1 Oracle contract.

@license Copyright (c) Curve.Fi, 2020-2024 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""


################################################################
#                           INTERFACES                         #
################################################################

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


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__(l1block_precompile_address: address):
    """
    @notice Deploys the contract and initializes the L1 oracle.
    @param l1block_precompile_address The address of the L1 block oracle.
    """
    L1BLOCK_ORACLE = IL1Block(l1block_precompile_address)
    self._fetch_latest_block()


################################################################
#                        INTERNAL FUNCTIONS                    #
################################################################

@internal
def _fetch_latest_block():
    """
    @notice Fetches the latest L1 block data if not already fetched.
    """
    block_number: uint64 = staticcall L1BLOCK_ORACLE.number()
    if not self._is_fetched(block_number):
        # Parse from oracle and store block data
        self.l1_blocks[block_number] = Block(
            block_hash=staticcall L1BLOCK_ORACLE.hash(),
            block_timestamp=staticcall L1BLOCK_ORACLE.timestamp(),
        )
        self.last_fetched_block = block_number


@internal
def _is_fetched(block_number: uint64) -> bool:
    """
    @notice Checks if block data has been fetched already.
    @param block_number The block number to check.
    @return True if fetched, False otherwise.
    """
    return self.l1_blocks[block_number].block_hash != empty(bytes32)


# @internal
# def _prove_previous_block(block_number: uint64, header_fields: bytes32[10]):


################################################################
#                      EXTERNAL FUNCTIONS                      #
################################################################

@external
def fetch_latest_block():
    """
    @notice Fetch the latest known block from the L1 oracle and store its number,
    hash, and timestamp.
    """
    self._fetch_latest_block()


@external
def get_block_hash(block_number: uint64) -> bytes32:
    """
    @notice Retrieve the block hash for a given block number.
    @param block_number The block number to get the hash for.
    @return The block hash for the given block number.
    """
    block_hash: bytes32 = self.l1_blocks[block_number].block_hash
    assert block_hash != empty(bytes32), "Block not fetched"
    return block_hash


@external
def get_block_timestamp(block_number: uint64) -> uint64:
    """
    @notice Retrieve the block timestamp for a given block number.
    @param block_number The block number to get the timestamp for.
    @return The block timestamp for the given block number.
    """
    block_timestamp: uint64 = self.l1_blocks[block_number].block_timestamp
    assert block_timestamp != 0, "Block not fetched"
    return block_timestamp


@external
def is_fetched(block_number: uint64) -> bool:
    """
    @notice Check if a block has been fetched.
    @param block_number The block number to check.
    @return True if the block has been fetched, False otherwise.
    """
    return self._is_fetched(block_number)


@external
def verify_preceeding_block(block_number: uint64, proof: Bytes[768]):
    """
    @notice Verify the previous block hash by submitting the block number and it's rlp encoded headers.
    @param block_number The block number to prove.
    @param proof Rlp encoded header fields of the current block.
    """
    current_block: Block = self.l1_blocks[block_number]
    assert self._is_fetched(block_number), "Block not fetched"
    if not self._is_fetched(block_number - 1):
        assert keccak256(proof) == current_block.block_hash, "Invalid proof"
        self.l1_blocks[block_number - 1] = Block(
            block_hash=convert(slice(proof, 4, 32), bytes32), # parentHash is the first one, preceeded by 4 bytes of rlp prefix
            block_timestamp=current_block.block_timestamp - 12, # approximation! may be wrong!
        )

################################################################
#                      VIEW FUNCTIONS                         #
################################################################

@external
@view
def peek_l1block_number() -> uint64:
    """
    @notice Peek the latest block number from the L1 oracle, without writing to storage.
    @return The latest block number from the L1 oracle.
    """
    return staticcall L1BLOCK_ORACLE.number()


# todo tomorrow
# develop blockhash prover, that would use checkpointed block and submitted headers of previous block to hash them and prove they are correct
