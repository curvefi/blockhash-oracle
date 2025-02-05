import boa


def test_default_behavior(block_oracle, dev_deployer):
    test_address = boa.env.generate_address()
    # validate the initial state
    assert not block_oracle.is_committer(test_address)
    assert block_oracle.num_committers() == 0

    # add committer
    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(test_address)
    assert block_oracle.is_committer(test_address)
    assert block_oracle.num_committers() == 1

    # remove committer
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(test_address)
    assert not block_oracle.is_committer(test_address)
    assert block_oracle.num_committers() == 0


def test_permission_add(block_oracle):
    test_address = boa.env.generate_address()
    # validate the initial state
    assert not block_oracle.is_committer(test_address)

    # add committer
    with boa.reverts("ownable: caller is not the owner"):
        block_oracle.add_committer(test_address)
    assert not block_oracle.is_committer(test_address)


def test_permission_remove(block_oracle, dev_deployer):
    test_address = boa.env.generate_address()
    # add mock committer
    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(test_address)
    assert block_oracle.is_committer(test_address)

    # attempt to remove it
    with boa.reverts("ownable: caller is not the owner"):
        block_oracle.remove_committer(test_address)
    assert block_oracle.is_committer(test_address)


def test_add_existing_committer(block_oracle, dev_deployer):
    """Test adding already existing committer"""
    test_address = boa.env.generate_address()
    assert block_oracle.num_committers() == 0

    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(test_address)
        assert block_oracle.num_committers() == 1

        # Try to add same committer again
        block_oracle.add_committer(test_address)

    assert block_oracle.num_committers() == 1


def test_remove_nonexistent_committer(block_oracle, dev_deployer):
    """Test removing non-existent committer"""
    test_address = boa.env.generate_address()
    assert block_oracle.num_committers() == 0
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(test_address)
        assert block_oracle.num_committers() == 0


def test_committer_list_integrity(block_oracle, dev_deployer):
    """Test that committer list maintains integrity after adds/removes"""
    committers = []

    # Add some committers
    for i in range(3):
        addr = boa.env.generate_address()
        committers.append(addr)
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(addr)

    # Remove middle committer
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(committers[1])

    # Verify remaining committers
    assert block_oracle.is_committer(committers[0])
    assert not block_oracle.is_committer(committers[1])
    assert block_oracle.is_committer(committers[2])
    assert block_oracle.num_committers() == 2
