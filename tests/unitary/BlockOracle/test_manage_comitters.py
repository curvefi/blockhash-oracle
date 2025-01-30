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
