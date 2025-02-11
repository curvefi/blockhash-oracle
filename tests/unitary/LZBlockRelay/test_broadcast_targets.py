import pytest
import boa
from eth_utils import to_checksum_address

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@pytest.fixture(scope="module")
def target_addresses():
    return [to_checksum_address(f"0x{i+1:040x}") for i in range(5)]


def test_add_broadcast_targets(lz_block_relay, dev_deployer, target_addresses):
    eids = [1, 2, 3]
    targets = target_addresses[:3]

    # Check that eids are empty
    for eid in eids:
        assert lz_block_relay.broadcast_targets(eid) == ZERO_ADDRESS
    assert len(lz_block_relay.all_broadcast_eids()) == 0

    # Add initial targets
    lz_block_relay.add_broadcast_targets(eids, targets, sender=dev_deployer)

    # Check targets were set correctly
    for eid, target in zip(eids, targets):
        assert lz_block_relay.broadcast_targets(eid) == target

    # Check eids list is correct
    broadcast_eids = lz_block_relay.all_broadcast_eids()
    assert len(broadcast_eids) == len(eids)
    assert set(broadcast_eids) == set(eids)


def test_add_broadcast_targets_overwrite(lz_block_relay, dev_deployer, target_addresses):
    eids = [1, 2]
    initial_targets = target_addresses[:2]
    new_targets = target_addresses[2:4]

    # Check initial state
    assert len(lz_block_relay.all_broadcast_eids()) == 0

    # Add initial targets
    lz_block_relay.add_broadcast_targets(eids, initial_targets, sender=dev_deployer)

    # Try to overwrite without _overwrite flag
    with pytest.raises(Exception, match="One of the targets already added"):
        lz_block_relay.add_broadcast_targets(eids, new_targets, sender=dev_deployer)

    # Overwrite with flag
    lz_block_relay.add_broadcast_targets(eids, new_targets, True, sender=dev_deployer)

    # Check targets were updated
    for eid, target in zip(eids, new_targets):
        assert lz_block_relay.broadcast_targets(eid) == target

    # Check eids list didn't grow
    broadcast_eids = lz_block_relay.all_broadcast_eids()
    assert len(broadcast_eids) == len(eids)
    assert set(broadcast_eids) == set(eids)


def test_add_broadcast_targets_mixed_overwrite(lz_block_relay, dev_deployer, target_addresses):
    # Test scenario where some targets exist and some don't
    eids = [1, 2, 3]
    initial_targets = target_addresses[:2]

    # Check initial state
    assert len(lz_block_relay.all_broadcast_eids()) == 0

    # Add initial targets for eids 1 and 2
    lz_block_relay.add_broadcast_targets(eids[:2], initial_targets, sender=dev_deployer)

    # Try to add for 1,2,3 with new addresses
    new_targets = target_addresses[2:5]
    lz_block_relay.add_broadcast_targets(eids, new_targets, True, sender=dev_deployer)

    # Check all targets were set
    for eid, target in zip(eids, new_targets):
        assert lz_block_relay.broadcast_targets(eid) == target

    # Check eids list includes the new eid
    broadcast_eids = lz_block_relay.all_broadcast_eids()
    assert len(broadcast_eids) == len(eids)
    assert set(broadcast_eids) == set(eids)


def test_remove_broadcast_targets(lz_block_relay, dev_deployer, target_addresses):
    eids = [1, 2, 3, 4]
    targets = target_addresses[:4]

    # Check initial state
    assert len(lz_block_relay.all_broadcast_eids()) == 0

    # Add initial targets
    lz_block_relay.add_broadcast_targets(eids, targets, sender=dev_deployer)

    # Remove some targets
    to_remove = eids[1:3]  # Remove eids 2 and 3
    lz_block_relay.remove_broadcast_targets(to_remove, sender=dev_deployer)

    # Check removed targets are zeroed
    for eid in to_remove:
        assert lz_block_relay.broadcast_targets(eid) == ZERO_ADDRESS

    # Check remaining targets are unchanged
    remaining = [eids[0], eids[3]]  # eids 1 and 4
    for eid, target in zip(remaining, [targets[0], targets[3]]):
        assert lz_block_relay.broadcast_targets(eid) == target

    # Check eids list is updated
    broadcast_eids = lz_block_relay.all_broadcast_eids()
    assert len(broadcast_eids) == len(remaining)
    assert set(broadcast_eids) == set(remaining)


def test_remove_broadcast_targets_ignore_missing(lz_block_relay, dev_deployer, target_addresses):
    eids = [1, 2]
    targets = target_addresses[:2]

    # Check initial state
    assert len(lz_block_relay.all_broadcast_eids()) == 0

    # Add initial targets
    lz_block_relay.add_broadcast_targets(eids, targets, sender=dev_deployer)

    # Try to remove existing and non-existing targets without ignore flag
    with pytest.raises(Exception, match="Not a target"):
        lz_block_relay.remove_broadcast_targets([1, 3], sender=dev_deployer)

    # Remove with ignore flag
    lz_block_relay.remove_broadcast_targets([1, 3], True, sender=dev_deployer)

    # Check eid 1 was removed
    assert lz_block_relay.broadcast_targets(1) == ZERO_ADDRESS

    # Check eid 2 is unchanged
    assert lz_block_relay.broadcast_targets(2) == targets[1]

    # Check eids list is correct
    broadcast_eids = lz_block_relay.all_broadcast_eids()
    assert len(broadcast_eids) == 1
    assert broadcast_eids[0] == 2


def test_only_owner(lz_block_relay, target_addresses):
    eids = [1]
    targets = target_addresses[:1]
    non_owner = boa.env.generate_address()

    # Try to add targets as non-owner
    with pytest.raises(Exception):
        lz_block_relay.add_broadcast_targets(eids, targets, sender=non_owner)

    # Try to remove targets as non-owner
    with pytest.raises(Exception):
        lz_block_relay.remove_broadcast_targets(eids, sender=non_owner)
