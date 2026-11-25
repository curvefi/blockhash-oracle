import boa
import pytest


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@pytest.fixture
def dao_emergency():
    return boa.env.generate_address()


@pytest.fixture
def dao_agent():
    return boa.env.generate_address()


@pytest.fixture
def owner_proxy(block_oracle, dao_emergency, dao_agent):
    return boa.load(
        "contracts/OwnerProxy.vy",
        block_oracle.address,
        dao_emergency,
        dao_agent,
    )


@pytest.fixture
def controlled_owner_proxy(block_oracle, owner_proxy, dev_deployer):
    with boa.env.prank(dev_deployer):
        block_oracle.transfer_ownership(owner_proxy.address)
    return owner_proxy


def test_constructor_validation(block_oracle):
    role_one = boa.env.generate_address()
    role_two = boa.env.generate_address()

    with boa.reverts("Invalid oracle"):
        boa.load("contracts/OwnerProxy.vy", ZERO_ADDRESS, role_one, role_two)

    with boa.reverts("Invalid dao_emergency"):
        boa.load("contracts/OwnerProxy.vy", block_oracle.address, ZERO_ADDRESS, role_two)

    with boa.reverts("Invalid dao_agent"):
        boa.load("contracts/OwnerProxy.vy", block_oracle.address, role_one, ZERO_ADDRESS)


def test_initial_state(block_oracle, owner_proxy, dao_emergency, dao_agent):
    assert owner_proxy.block_oracle() == block_oracle.address
    assert owner_proxy.dao_emergency() == dao_emergency
    assert owner_proxy.dao_agent() == dao_agent


@pytest.mark.parametrize("role_name", ["dao_emergency", "dao_agent"])
def test_each_role_can_call_all_oracle_wrappers(
    controlled_owner_proxy,
    block_oracle,
    block_headers_decoder,
    dao_emergency,
    dao_agent,
    role_name,
):
    caller = dao_emergency if role_name == "dao_emergency" else dao_agent
    committer = boa.env.generate_address()
    block_number = 12345
    block_hash = b"\x11" * 32

    with boa.env.prank(caller):
        controlled_owner_proxy.set_header_verifier(block_headers_decoder.address)
        controlled_owner_proxy.add_committer(committer, True)
        controlled_owner_proxy.set_threshold(1)
        controlled_owner_proxy.admin_apply_block(block_number, block_hash)
        controlled_owner_proxy.remove_committer(committer)

    assert block_oracle.header_verifier() == block_headers_decoder.address
    assert not block_oracle.is_committer(committer)
    assert block_oracle.threshold() == 1
    assert block_oracle.get_block_hash(block_number) == block_hash


def test_outsider_cannot_call_wrappers(controlled_owner_proxy):
    outsider = boa.env.generate_address()

    with boa.env.prank(outsider):
        with boa.reverts("Not authorized"):
            controlled_owner_proxy.set_threshold(1)


@pytest.mark.parametrize("caller_role", ["dao_emergency", "dao_agent"])
def test_any_admin_can_rotate_dao_emergency(
    controlled_owner_proxy, block_headers_decoder, dao_emergency, dao_agent, caller_role
):
    new_emergency = boa.env.generate_address()
    caller = dao_emergency if caller_role == "dao_emergency" else dao_agent

    with boa.env.prank(caller):
        controlled_owner_proxy.set_dao_emergency(new_emergency)

    assert controlled_owner_proxy.dao_emergency() == new_emergency

    with boa.env.prank(dao_emergency):
        with boa.reverts("Not authorized"):
            controlled_owner_proxy.set_header_verifier(block_headers_decoder.address)

    with boa.env.prank(new_emergency):
        controlled_owner_proxy.set_header_verifier(block_headers_decoder.address)


@pytest.mark.parametrize("caller_role", ["dao_emergency", "dao_agent"])
def test_any_admin_can_rotate_dao_agent(
    controlled_owner_proxy, block_headers_decoder, dao_emergency, dao_agent, caller_role
):
    new_agent = boa.env.generate_address()
    caller = dao_emergency if caller_role == "dao_emergency" else dao_agent

    with boa.env.prank(caller):
        controlled_owner_proxy.set_dao_agent(new_agent)

    assert controlled_owner_proxy.dao_agent() == new_agent

    with boa.env.prank(dao_agent):
        with boa.reverts("Not authorized"):
            controlled_owner_proxy.set_header_verifier(block_headers_decoder.address)

    with boa.env.prank(new_agent):
        controlled_owner_proxy.set_header_verifier(block_headers_decoder.address)


def test_role_rotation_rejects_zero_address(controlled_owner_proxy, dao_emergency, dao_agent):
    with boa.env.prank(dao_emergency):
        with boa.reverts("Invalid dao_emergency"):
            controlled_owner_proxy.set_dao_emergency(ZERO_ADDRESS)

    with boa.env.prank(dao_agent):
        with boa.reverts("Invalid dao_agent"):
            controlled_owner_proxy.set_dao_agent(ZERO_ADDRESS)


def test_same_address_can_hold_and_rotate_both_roles(block_oracle, dev_deployer):
    shared_admin = boa.env.generate_address()
    new_emergency = boa.env.generate_address()
    new_agent = boa.env.generate_address()

    proxy = boa.load(
        "contracts/OwnerProxy.vy",
        block_oracle.address,
        shared_admin,
        shared_admin,
    )

    with boa.env.prank(dev_deployer):
        block_oracle.transfer_ownership(proxy.address)

    with boa.env.prank(shared_admin):
        proxy.set_dao_emergency(new_emergency)
        proxy.set_dao_agent(new_agent)

    assert proxy.dao_emergency() == new_emergency
    assert proxy.dao_agent() == new_agent


@pytest.mark.parametrize("role_name", ["dao_emergency", "dao_agent"])
def test_either_role_can_transfer_oracle_ownership_away(
    controlled_owner_proxy,
    block_oracle,
    block_headers_decoder,
    dao_emergency,
    dao_agent,
    role_name,
):
    caller = dao_emergency if role_name == "dao_emergency" else dao_agent
    new_owner = boa.env.generate_address()

    with boa.env.prank(caller):
        controlled_owner_proxy.transfer_block_oracle_ownership(new_owner)

    assert block_oracle.owner() == new_owner

    with boa.env.prank(dao_emergency):
        with boa.reverts("ownable: caller is not the owner"):
            controlled_owner_proxy.set_header_verifier(block_headers_decoder.address)
