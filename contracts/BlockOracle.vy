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

initializes: ownable
exports: (
    ownable.owner,
    ownable.transfer_ownership,
    ownable.renounce_ownership,
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

block_hash: public(HashMap[uint256, bytes32])  # block_number => hash
last_confirmed_block_number: public(uint256)

num_committers: public(uint256)
is_committer: public(HashMap[address, bool])
commitment_count: public(HashMap[uint256, HashMap[bytes32, uint256]])  # block_number => hash => count
committer_votes: public(HashMap[address, HashMap[uint256, bytes32]])  # committer => block_number => committed_hash
threshold: public(uint256)


@deploy
def __init__(_threshold: uint256, _owner: address):
    self.threshold = _threshold
    self.num_committers = 0
    ownable.__init__()
    ownable._transfer_ownership(_owner)

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
    if not self.is_committer[_committer]:
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
    if self.is_committer[_committer]:
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
    @dev All security checks must be performed outside!
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

    previous_commitment: bytes32 = self.committer_votes[msg.sender][block_number]

    # Remove previous vote if exists, to avoid duplicate commitments
    if previous_commitment != empty(bytes32):
        self.commitment_count[block_number][previous_commitment] -= 1

    self.committer_votes[msg.sender][block_number] = block_hash
    self.commitment_count[block_number][block_hash] += 1
    log CommitBlock(msg.sender, block_number, block_hash)

    # Optional attempt to apply block
    if apply:
        count: uint256 = self.commitment_count[block_number][block_hash]
        if count >= self.threshold:
            self._apply_block(block_number, block_hash)
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
    assert self.commitment_count[block_number][block_hash] >= self.threshold, "Insufficient commitments"
    self._apply_block(block_number, block_hash)
