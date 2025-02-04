import pytest
import boa


@pytest.fixture
def committers(block_oracle, dev_deployer):
    res = []
    for i in range(5):
        committer_address = boa.env.generate_address()
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(committer_address)
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
