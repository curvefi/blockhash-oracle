# pragma version 0.4.3
# pragma optimize gas

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

# Import RLP Block Header Decoder
from modules import BlockHeaderRLPDecoder as bh_rlp

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


event SubmitBlockHeader:
    block_number: indexed(uint256)
    block_hash: bytes32


event AddCommitter:
    committer: indexed(address)


event RemoveCommitter:
    committer: indexed(address)


event SetThreshold:
    new_threshold: indexed(uint256)


event SetHeaderVerifier:
    old_verifier: indexed(address)
    new_verifier: indexed(address)


################################################################
#                            CONSTANTS                          #
################################################################

MAX_COMMITTERS: constant(uint256) = 32


################################################################
#                            STORAGE                           #
################################################################

block_hash: HashMap[uint256, bytes32]  # block_number => hash
last_confirmed_block_number: public(uint256)  # number of the last confirmed block hash
header_verifier: public(address)  # address of the header verifier

block_header: public(HashMap[uint256, bh_rlp.BlockHeader])  # block_number => header
last_confirmed_header: public(bh_rlp.BlockHeader)  # last confirmed header

committers: public(DynArray[address, MAX_COMMITTERS])  # List of all committers
is_committer: public(HashMap[address, bool])
commitment_count: public(
    HashMap[uint256, HashMap[bytes32, uint256]]
)  # block_number => hash => count
committer_votes: public(
    HashMap[address, HashMap[uint256, bytes32]]
)  # committer => block_number => committed_hash
threshold: public(uint256)


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__():
    """
    @notice Initialize the contract with the owner
    """

    # Initialize ownable
    ownable.__init__()
    # tx.origin in case of proxy deployment
    ownable._transfer_ownership(tx.origin)


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

@external
def set_header_verifier(_verifier: address):
    """
    @notice Set the block header verifier
    @dev Emits SetHeaderVerifier event
    @param _verifier Address of the block header verifier
    """

    ownable._check_owner()
    old_verifier: address = self.header_verifier
    self.header_verifier = _verifier
    log SetHeaderVerifier(old_verifier=old_verifier, new_verifier=_verifier)


@external
def add_committer(_committer: address, _bump_threshold: bool = False):
    """
    @notice Set trusted address that can commit block data
    @param _committer Address of trusted committer
    @param _bump_threshold If True, bump threshold to 1 more (useful for initial setup)
    """

    ownable._check_owner()
    if not self.is_committer[_committer]:
        assert len(self.committers) < MAX_COMMITTERS, "Max committers reached"
        self.is_committer[_committer] = True
        self.committers.append(_committer)
        log AddCommitter(committer=_committer)

        if _bump_threshold:
            self.threshold += 1


@external
def remove_committer(_committer: address):
    """
    @notice Remove trusted address that can commit block data
    @param _committer Address of trusted committer
    """

    ownable._check_owner()
    if self.is_committer[_committer]:
        self.is_committer[_committer] = False

        # Rebuild committers array excluding the removed committer
        new_committers: DynArray[address, MAX_COMMITTERS] = []
        for committer: address in self.committers:
            if committer != _committer:
                new_committers.append(committer)
        self.committers = new_committers

        log RemoveCommitter(committer=_committer)


@external
def set_threshold(_new_threshold: uint256):
    """
    @notice Update threshold for block application
    @param _new_threshold New threshold value
    """

    ownable._check_owner()
    assert _new_threshold <= len(
        self.committers
    ), "Threshold cannot be greater than number of committers"
    assert _new_threshold > 0, "Threshold must be greater than 0"
    self.threshold = _new_threshold

    log  SetThreshold(new_threshold=_new_threshold)


@external
def admin_apply_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Apply a block hash with admin rights
    @param _block_number The block number to apply
    @param _block_hash The hash to apply
    @dev Only callable by owner
    """

    ownable._check_owner()
    self._apply_block(_block_number, _block_hash)


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
def _apply_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Confirm a block hash and apply it
    @dev All security checks must be performed outside!
    @param _block_number The block number to confirm
    @param _block_hash The hash to confirm
    """

    self.block_hash[_block_number] = _block_hash
    if self.last_confirmed_block_number < _block_number:
        self.last_confirmed_block_number = _block_number
    log ApplyBlock(block_number=_block_number, block_hash=_block_hash)


################################################################
#                  PERMISSIONED FUNCTIONS                      #
################################################################

@external
def commit_block(_block_number: uint256, _block_hash: bytes32, _apply: bool = True) -> bool:
    """
    @notice Commit a block hash and optionally attempt to apply it
    @param _block_number The block number to commit
    @param _block_hash The hash to commit
    @param _apply If True, checks if threshold is met and applies block
    @return True if block was applied
    """

    assert self.is_committer[msg.sender], "Not authorized"
    assert self.threshold > 0, "Threshold not set"
    assert self.block_hash[_block_number] == empty(bytes32), "Already applied"
    assert _block_hash != empty(bytes32), "Invalid block hash"

    previous_commitment: bytes32 = self.committer_votes[msg.sender][_block_number]

    # Remove previous vote if exists, to avoid duplicate commitments
    if previous_commitment != empty(bytes32):
        self.commitment_count[_block_number][previous_commitment] -= 1

    self.committer_votes[msg.sender][_block_number] = _block_hash
    self.commitment_count[_block_number][_block_hash] += 1
    log CommitBlock(committer=msg.sender, block_number=_block_number, block_hash=_block_hash)

    # Optional attempt to apply block
    if _apply and self.commitment_count[_block_number][_block_hash] >= self.threshold:
        self._apply_block(_block_number, _block_hash)
        return True
    return False


@external
def submit_block_header(_header_data: bh_rlp.BlockHeader):
    """
    @notice Submit block header. Available only to whitelisted verifier contract.
    @param _header_data The block header to submit
    """
    assert msg.sender == self.header_verifier, "Not authorized"

    # Safety checks
    assert _header_data.block_hash != empty(bytes32), "Invalid block hash"
    assert self.block_hash[_header_data.block_number] != empty(bytes32), "Blockhash not applied"
    assert _header_data.block_hash == self.block_hash[_header_data.block_number], "Blockhash does not match"
    assert self.block_header[_header_data.block_number].block_hash == empty(bytes32), "Header already submitted"

    # Store decoded header
    self.block_header[_header_data.block_number] = _header_data

    # Update last confirmed header if new
    if _header_data.block_number > self.last_confirmed_header.block_number:
        self.last_confirmed_header = _header_data

    log SubmitBlockHeader(
        block_number=_header_data.block_number,
        block_hash=_header_data.block_hash,
    )


################################################################
#                 PERMISSIONLESS FUNCTIONS                     #
################################################################

@external
def apply_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Apply a block hash if it has sufficient commitments
    @param _block_number The block number to apply
    @param _block_hash The block hash to apply
    """
    assert self.threshold > 0, "Threshold not set"
    assert self.block_hash[_block_number] == empty(bytes32), "Already applied"
    assert (
        self.commitment_count[_block_number][_block_hash] >= self.threshold
    ), "Insufficient commitments"
    self._apply_block(_block_number, _block_hash)


################################################################
#                         VIEW FUNCTIONS                       #
################################################################

@view
@external
def get_all_committers() -> DynArray[address, MAX_COMMITTERS]:
    """
    @notice Utility viewer that returns list of all committers
    @return Array of all registered committer addresses
    """
    return self.committers


@view
@external
def get_block_hash(_block_number: uint256) -> bytes32:
    """
    @notice Get the confirmed block hash for a given block number
    @param _block_number The block number to query
    @return The confirmed block hash, or empty bytes32 if not confirmed
    """
    return self.block_hash[_block_number]


@view
@external
def get_state_root(_block_number: uint256) -> bytes32:
    """
    @notice Get the state root for a given block number
    @param _block_number The block number to query
    @return The state root from the block header, or empty bytes32 if header not submitted
    """
    return self.block_header[_block_number].state_root
