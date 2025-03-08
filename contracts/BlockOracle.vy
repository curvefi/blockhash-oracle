# pragma version ~=0.4
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

initializes: bh_rlp


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
    committer: indexed(address)
    block_number: indexed(uint256)
    block_hash: bytes32


event AddCommitter:
    committer: indexed(address)


event RemoveCommitter:
    committer: indexed(address)


################################################################
#                            CONSTANTS                          #
################################################################

MAX_COMMITTERS: constant(uint256) = 32


################################################################
#                            STORAGE                           #
################################################################

block_hash: public(HashMap[uint256, bytes32])  # block_number => hash
last_confirmed_block_number: public(uint256)  # number of the last confirmed block hash

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
def __init__(_owner: address):
    """
    @notice Initialize the contract with the owner
    @param _owner The owner of the contract
    """

    # Initialize ownable
    ownable.__init__()
    ownable._transfer_ownership(_owner)

    # Initialize RLP decoder
    bh_rlp.__init__()


################################################################
#                      OWNER FUNCTIONS                         #
################################################################

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
        log AddCommitter(_committer)

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

        log RemoveCommitter(_committer)


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
    self.threshold = _new_threshold


@external
def admin_apply_block(block_number: uint256, block_hash: bytes32):
    """
    @notice Apply a block hash with admin rights
    @param block_number The block number to apply
    @param block_hash The hash to apply
    @dev Only callable by owner
    """

    ownable._check_owner()
    self._apply_block(block_number, block_hash)


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
    assert block_hash != empty(bytes32), "Invalid block hash"

    previous_commitment: bytes32 = self.committer_votes[msg.sender][block_number]

    # Remove previous vote if exists, to avoid duplicate commitments
    if previous_commitment != empty(bytes32):
        self.commitment_count[block_number][previous_commitment] -= 1

    self.committer_votes[msg.sender][block_number] = block_hash
    self.commitment_count[block_number][block_hash] += 1
    log CommitBlock(msg.sender, block_number, block_hash)

    # Optional attempt to apply block
    if apply and self.commitment_count[block_number][block_hash] >= self.threshold:
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
    assert (
        self.commitment_count[block_number][block_hash] >= self.threshold
    ), "Insufficient commitments"
    self._apply_block(block_number, block_hash)


@external
def submit_block_header(encoded_header: Bytes[bh_rlp.BLOCK_HEADER_SIZE]):
    """
    @notice Submit a block header. If it's correct and blockhash is applied, store it.
    @param encoded_header The block header to submit
    """
    current_header_block_number: uint256 = self.last_confirmed_header.block_number
    # Decode whatever is submitted
    decoded_header: bh_rlp.BlockHeader = bh_rlp._decode_block_header(encoded_header)

    # Validate against stored blockhash
    block_hash: bytes32 = self.block_hash[decoded_header.block_number]
    assert block_hash != empty(bytes32), "Blockhash not applied"
    assert (decoded_header.block_hash == block_hash), "Blockhash does not match"
    assert self.block_header[decoded_header.block_number] == empty(
        bh_rlp.BlockHeader
    ), "Header already submitted"

    # Store decoded header
    self.block_header[decoded_header.block_number] = decoded_header
    log SubmitBlockHeader(msg.sender, decoded_header.block_number, decoded_header.block_hash)

    if decoded_header.block_number > current_header_block_number:
        self.last_confirmed_header = decoded_header


################################################################
#                         VIEW FUNCTIONS                       #
################################################################

@view
@external
def get_all_committers() -> DynArray[address, MAX_COMMITTERS]:
    """
    @notice Utility viewer that returns list of all committers
    """
    return self.committers


@view
@external
def get_block_hash(block_number: uint256) -> bytes32:
    return self.block_hash[block_number]


@view
@external
def get_state_root(block_number: uint256) -> bytes32:
    return self.block_header[block_number].state_root
