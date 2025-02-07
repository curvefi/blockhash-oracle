import boa


def test_default_behavior(block_oracle, dev_deployer):
    test_address = boa.env.generate_address()
    # validate the initial state
    assert not block_oracle.is_committer(test_address)
    assert len(block_oracle.get_all_committers()) == 0

    # add committer
    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(test_address)
    assert block_oracle.is_committer(test_address)
    assert len(block_oracle.get_all_committers()) == 1

    # remove committer
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(test_address)
    assert not block_oracle.is_committer(test_address)
    assert len(block_oracle.get_all_committers()) == 0


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
    assert len(block_oracle.get_all_committers()) == 0

    with boa.env.prank(dev_deployer):
        block_oracle.add_committer(test_address)
        assert len(block_oracle.get_all_committers()) == 1

        # Try to add same committer again
        block_oracle.add_committer(test_address)

    assert len(block_oracle.get_all_committers()) == 1


def test_remove_nonexistent_committer(block_oracle, dev_deployer):
    """Test removing non-existent committer"""
    test_address = boa.env.generate_address()
    assert len(block_oracle.get_all_committers()) == 0
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(test_address)
        assert len(block_oracle.get_all_committers()) == 0


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
    assert len(block_oracle.get_all_committers()) == 2


def test_max_committers_limit(block_oracle, dev_deployer):
    """Test that MAX_COMMITTERS limit is enforced"""
    MAX_COMMITTERS = 32  # Match constant from contract

    # Add maximum number of committers
    committers = []
    for i in range(MAX_COMMITTERS):
        addr = boa.env.generate_address()
        committers.append(addr)
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(addr)

    # Verify state
    assert len(block_oracle.get_all_committers()) == MAX_COMMITTERS

    # Try to add one more
    with boa.reverts("Max committers reached"):
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(boa.env.generate_address())


def test_committer_order_preservation(block_oracle, dev_deployer):
    """Test that committer order is preserved after removals"""
    committers = []

    # Add 5 committers
    for i in range(5):
        addr = boa.env.generate_address()
        committers.append(addr)
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(addr)

    # Remove committers 1 and 3
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(committers[1])
        block_oracle.remove_committer(committers[3])

    # Check remaining committers are in correct order
    remaining = block_oracle.get_all_committers()
    assert remaining == [committers[0], committers[2], committers[4]]


def test_threshold_with_committer_removal(block_oracle, dev_deployer):
    """Test threshold behavior when removing committers"""
    # Add 3 committers and set threshold to 3
    committers = []
    for i in range(3):
        addr = boa.env.generate_address()
        committers.append(addr)
        with boa.env.prank(dev_deployer):
            block_oracle.add_committer(addr)

    with boa.env.prank(dev_deployer):
        block_oracle.set_threshold(3)

    # Remove a committer
    with boa.env.prank(dev_deployer):
        block_oracle.remove_committer(committers[0])

    # Try to set threshold higher than remaining committers
    with boa.reverts("Threshold cannot be greater than number of committers"):
        with boa.env.prank(dev_deployer):
            block_oracle.set_threshold(3)
