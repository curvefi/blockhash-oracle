# pragma version ~=0.4

"""
@title Block Oracle

@notice Decentralized block hash oracle with multi-committer consensus
Uses a threshold-based commitment system where trusted committers can submit and validate block hashes
Notable features are:
    - Committers can submit block hashes and optionally trigger validation
    - Each block requires threshold number of matching commitments to be confirmed
    - Committers can update their votes before confirmation
    - Once confirmed, block hashes are immutable
    - Owner can manage committers and adjust threshold

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

################################################################
#                            MODULES                           #
################################################################

# Import ownership management
from snekmate.auth import ownable
from snekmate.auth import ownable_2step

initializes: ownable
initializes: ownable_2step[ownable := ownable]
exports: (
    ownable_2step.owner,
    ownable_2step.pending_owner,
    ownable_2step.transfer_ownership,
    ownable_2step.accept_ownership,
    ownable_2step.renounce_ownership,
)

################################################################
#                            EVENTS                            #
################################################################

event CommitBlock:
    committer: indexed(address)
    block_number: indexed(uint256)
    block_hash: bytes32


event ApplyBlock:
    block_number: indexed(uint256)
    block_hash: bytes32

event AddCommitter:
    committer: indexed(address)

event RemoveCommitter:
    committer: indexed(address)

################################################################
#                            STORAGE                           #
################################################################

is_committer: public(HashMap[address, bool])
commitments: HashMap[uint256, HashMap[bytes32, uint256]]  # block_number => hash => count
committer_votes: HashMap[uint256, HashMap[address, bytes32]]  # block_number => committer => committed_hash

block_hash: public(HashMap[uint256, bytes32])  # block_number => hash
threshold: public(uint256)
num_committers: public(uint256)
last_confirmed_block_number: public(uint256)

struct Commitment:
    hash: bytes32
    count: uint256


@deploy
def __init__(_threshold: uint256):
    self.threshold = _threshold
    self.num_committers = 0
    ownable.__init__()
    ownable_2step.__init__()


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def add_committer(_committer: address):
    """
    @notice Set trusted address that can commit block data
    @param _committer Address of trusted committer
    """
    ownable._check_owner()
    self.is_committer[_committer] = True
    self.num_committers += 1
    log AddCommitter(_committer)

@external
def remove_committer(_committer: address):
    """
    @notice Remove trusted address that can commit block data
    @param _committer Address of trusted committer
    """
    ownable._check_owner()
    self.is_committer[_committer] = False
    self.num_committers -= 1
    log RemoveCommitter(_committer)


@external
def set_threshold(_new_threshold: uint256):
    """
    @notice Update threshold for block application
    @param _new_threshold New threshold value
    """
    ownable._check_owner()
    self.threshold = _new_threshold


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
def _apply_block(block_number: uint256, block_hash: bytes32):
    """
    @notice Confirm a block hash and apply it
    @param block_number The block number to confirm
    @param block_hash The hash to confirm
    """
    self.block_hash[block_number] = block_hash
    if self.last_confirmed_block_number < block_number:
        self.last_confirmed_block_number = block_number
    log ApplyBlock(block_number, block_hash)


################################################################
#                  PERMISSIONED FUNCTIONS                      #
################################################################

@external
def commit_block(block_number: uint256, block_hash: bytes32, apply: bool = True) -> bool:
    """
    @notice Commit a block hash and optionally attempt to apply it
    @param block_number The block number to commit
    @param block_hash The hash to commit
    @param apply If True, checks if threshold is met and applies block
    @return True if block was applied
    """
    assert self.is_committer[msg.sender], "Not authorized"
    assert self.block_hash[block_number] == empty(bytes32), "Already applied"

    previous_commitment: bytes32 = self.committer_votes[block_number][msg.sender]

    # Remove previous vote if exists, to avoid duplicate commitments
    if previous_commitment != empty(bytes32):
        self.commitments[block_number][previous_commitment] -= 1

    self.committer_votes[block_number][msg.sender] = block_hash
    self.commitments[block_number][block_hash] += 1
    log CommitBlock(msg.sender, block_number, block_hash)

    # Optional attempt to apply block
    if apply:
        count: uint256 = self.commitments[block_number][block_hash]
        if count >= self.threshold:
            self._apply_block(block_number, block_hash)
            self.block_hash[block_number] = block_hash
            log ApplyBlock(block_number, block_hash)
            if self.last_confirmed_block_number < block_number:
                self.last_confirmed_block_number = block_number
            return True
    return False


################################################################
#                 PERMISSIONLESS FUNCTIONS                     #
################################################################

@external
def apply_block(block_number: uint256, block_hash: bytes32):
    """
    @notice Apply a block hash if it has sufficient commitments
    """
    assert self.block_hash[block_number] == empty(bytes32), "Already applied"
    assert self.commitments[block_number][block_hash] >= self.threshold, "Insufficient commitments"
    self._apply_block(block_number, block_hash)


################################################################
#                       VIEW FUNCTIONS                         #
################################################################

@view
@external
def get_commitment_count(block_number: uint256, block_hash: bytes32) -> uint256:
    """
    @notice Get number of commitments for a specific block hash
    """
    return self.commitments[block_number][block_hash]

@view
@external
def get_committer_vote(block_number: uint256, committer: address) -> bytes32:
    """
    @notice Get the hash that a committer voted for at given block
    @param block_number Block number to check
    @param committer Address of the committer
    @return Hash that committer voted for, or empty bytes if no vote
    """
    return self.committer_votes[block_number][committer]


# @external
# def foo():
#     print("hello vyper 🐍")
