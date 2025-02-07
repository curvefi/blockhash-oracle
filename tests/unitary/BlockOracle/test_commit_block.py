import pytest
import boa


@pytest.fixture
def committers(block_oracle, dev_deployer):
    res = []
    for i in range(5):
        committer_address = boa.env.generate_address()
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(committer_address, True if i == 0 else False)
        res.append(committer_address)
    return res


def test_default_behavior(block_oracle, committers):
    committer = committers[0]
    # single committer operating on a threshold of 1
    assert block_oracle.is_committer(committer)
    assert block_oracle.threshold() == 1
    # some mock block data
    mock_block_hash = b"\x01" * 32
    mock_block_num = 11223344
    # initial state - empty(bytes32)
    assert block_oracle.block_hash(mock_block_num) == b"\x00" * 32

    # commit and apply
    with boa.env.prank(committer):
        block_oracle.commit_block(mock_block_num, mock_block_hash)

    # assert change
    assert block_oracle.block_hash(mock_block_num) == mock_block_hash


def test_multiple_committers_consensus(block_oracle, committers, dev_deployer):
    mock_block_hash = b"\x01" * 32
    mock_block_num = 11223344

    # Set threshold to 3
    with boa.env.prank(dev_deployer):
        block_oracle.set_threshold(3)

    # First two commits shouldn't apply block
    for i in range(2):
        with boa.env.prank(committers[i]):
            assert not block_oracle.commit_block(mock_block_num, mock_block_hash)
            assert block_oracle.commitment_count(mock_block_num, mock_block_hash) == i + 1
            assert block_oracle.block_hash(mock_block_num) == b"\x00" * 32

    # Third commit should apply
    with boa.env.prank(committers[2]):
        assert block_oracle.commit_block(mock_block_num, mock_block_hash)
        assert block_oracle.block_hash(mock_block_num) == mock_block_hash


def test_vote_changes(block_oracle, committers):
    mock_block_hash1 = b"\x01" * 32
    mock_block_hash2 = b"\x02" * 32
    mock_block_num = 11223344

    with boa.env.prank(block_oracle.owner()):
        block_oracle.set_threshold(2)

    # First committer votes for hash1
    with boa.env.prank(committers[0]):
        block_oracle.commit_block(mock_block_num, mock_block_hash1, False)
        assert block_oracle.commitment_count(mock_block_num, mock_block_hash1) == 1

    # Same committer changes vote to hash2
    with boa.env.prank(committers[0]):
        block_oracle.commit_block(mock_block_num, mock_block_hash2, False)
        assert block_oracle.commitment_count(mock_block_num, mock_block_hash1) == 0
        assert block_oracle.commitment_count(mock_block_num, mock_block_hash2) == 1


def test_competing_hashes(block_oracle, committers):
    hash1 = b"\x01" * 32
    hash2 = b"\x02" * 32
    block_num = 11223344

    with boa.env.prank(block_oracle.owner()):
        block_oracle.set_threshold(3)

    # Two committers vote for hash1
    for i in range(2):
        with boa.env.prank(committers[i]):
            block_oracle.commit_block(block_num, hash1, False)

    # Two different committers vote for hash2
    for i in range(2, 4):
        with boa.env.prank(committers[i]):
            block_oracle.commit_block(block_num, hash2, False)

    assert block_oracle.commitment_count(block_num, hash1) == 2
    assert block_oracle.commitment_count(block_num, hash2) == 2

    # Final vote for hash1 should confirm it
    with boa.env.prank(committers[4]):
        assert block_oracle.commit_block(block_num, hash1)
        assert block_oracle.block_hash(block_num) == hash1


def test_permission_commit(block_oracle):
    """Test that non-committers cannot commit blocks"""
    random_address = boa.env.generate_address()
    mock_block_hash = b"\x01" * 32
    mock_block_num = 11223344

    with boa.reverts("Not authorized"):
        with boa.env.prank(random_address):
            block_oracle.commit_block(mock_block_num, mock_block_hash)


def test_double_commit_same_hash(block_oracle, committers):
    """Test that same committer cannot commit same hash twice"""
    mock_block_hash = b"\x01" * 32
    mock_block_num = 11223344

    with boa.env.prank(committers[0]):
        block_oracle.commit_block(mock_block_num, mock_block_hash, False)
        # Second commit should fail or have no effect
        assert not block_oracle.commit_block(mock_block_num, mock_block_hash, False)
        assert block_oracle.commitment_count(mock_block_num, mock_block_hash) == 1


def test_block_already_committed(block_oracle, committers):
    """Test that block hash cannot be changed once committed"""
    mock_block_hash1 = b"\x01" * 32
    mock_block_hash2 = b"\x02" * 32
    mock_block_num = 11223344

    # First commit and apply hash1
    with boa.env.prank(committers[0]):
        block_oracle.commit_block(mock_block_num, mock_block_hash1)

    # Try to commit different hash
    with boa.reverts("Already applied"):
        block_oracle.commit_block(mock_block_num, mock_block_hash2, sender=committers[1])

    # Hash should remain unchanged
    assert block_oracle.block_hash(mock_block_num) == mock_block_hash1


def test_admin_apply_block(block_oracle, dev_deployer):
    """Test admin_apply_block functionality"""
    mock_block_num = 12345
    mock_hash = b"\x01" * 32

    # Non-owner cannot apply
    with boa.reverts("ownable: caller is not the owner"):
        block_oracle.admin_apply_block(mock_block_num, mock_hash)

    # Owner can apply
    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(mock_block_num, mock_hash)

    assert block_oracle.block_hash(mock_block_num) == mock_hash
    assert block_oracle.last_confirmed_block_number() == mock_block_num


def test_commit_after_admin_apply(block_oracle, committers, dev_deployer):
    """Test that commits are rejected after admin applies a block"""
    mock_block_num = 12345
    mock_hash = b"\x01" * 32
    different_hash = b"\x02" * 32

    # Admin applies block
    with boa.env.prank(dev_deployer):
        block_oracle.admin_apply_block(mock_block_num, mock_hash)

    # Try to commit same block
    with boa.reverts("Already applied"):
        with boa.env.prank(committers[0]):
            block_oracle.commit_block(mock_block_num, different_hash)


def test_last_confirmed_block_number(block_oracle, committers):
    """Test last_confirmed_block_number updates correctly"""
    blocks = [100, 200, 150, 300]  # Non-sequential blocks
    mock_hash = b"\x01" * 32
    max_committed = 0
    for block_num in blocks:
        with boa.env.prank(committers[0]):
            block_oracle.commit_block(block_num, mock_hash)
            max_committed = max(max_committed, block_num)
            # Should update only if greater than current
            assert block_oracle.last_confirmed_block_number() == max_committed


def test_apply_block_permissionless(block_oracle, committers):
    """Test permissionless apply_block function"""
    mock_block_num = 12345
    mock_hash = b"\x01" * 32

    # Set threshold to 2
    with boa.env.prank(block_oracle.owner()):
        block_oracle.set_threshold(2)

    # Have committers commit but not apply
    for i in range(2):
        with boa.env.prank(committers[i]):
            block_oracle.commit_block(mock_block_num, mock_hash, False)

    # Random address can trigger apply
    random_address = boa.env.generate_address()
    with boa.env.prank(random_address):
        block_oracle.apply_block(mock_block_num, mock_hash)
    result_hash = block_oracle.block_hash(mock_block_num)
    assert result_hash == mock_hash
