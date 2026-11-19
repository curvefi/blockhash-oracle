# pragma version 0.4.3
# pragma optimize gas

"""
@title Owner Proxy

@notice Narrow admin proxy for a single BlockOracle instance.
        Two fixed admin roles share the same oracle owner privileges
        and can rotate either role for recovery.

@license Copyright (c) Curve.Fi, 2026 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""


################################################################
#                          INTERFACES                          #
################################################################

interface IBlockOracleAdmin:
    def set_header_verifier(verifier: address): nonpayable
    def add_committer(committer: address, bump_threshold: bool): nonpayable
    def remove_committer(committer: address): nonpayable
    def set_threshold(new_threshold: uint256): nonpayable
    def admin_apply_block(block_number: uint256, block_hash: bytes32): nonpayable
    def transfer_ownership(new_owner: address): nonpayable



################################################################
#                            EVENTS                            #
################################################################

event DaoEmergencyUpdated:
    previous_role: indexed(address)
    new_role: indexed(address)


event DaoAgentUpdated:
    previous_role: indexed(address)
    new_role: indexed(address)


################################################################
#                            STORAGE                           #
################################################################

block_oracle: public(immutable(IBlockOracleAdmin))
dao_emergency: public(address)
dao_agent: public(address)


################################################################
#                         CONSTRUCTOR                          #
################################################################

@deploy
def __init__(_block_oracle: address, _dao_emergency: address, _dao_agent: address):
    """
    @notice Initialize proxy with one bound oracle and two admin roles.
    @param _block_oracle Address of the BlockOracle owned by this proxy
    @param _dao_emergency Emergency admin role
    @param _dao_agent DAO executor/agent role
    """
    assert _block_oracle != empty(address), "Invalid oracle"
    assert _dao_emergency != empty(address), "Invalid dao_emergency"
    assert _dao_agent != empty(address), "Invalid dao_agent"

    block_oracle = IBlockOracleAdmin(_block_oracle)
    self.dao_emergency = _dao_emergency
    self.dao_agent = _dao_agent


################################################################
#                     INTERNAL FUNCTIONS                       #
################################################################

@internal
@view
def _check_admin():
    assert (
        msg.sender == self.dao_emergency or msg.sender == self.dao_agent
    ), "Not authorized"


################################################################
#                      ROLE MANAGEMENT                         #
################################################################

@external
def set_dao_emergency(new_dao_emergency: address):
    """
    @notice Rotate the emergency role.
    @param new_dao_emergency New emergency admin
    """
    self._check_admin()
    assert new_dao_emergency != empty(address), "Invalid dao_emergency"

    old_role: address = self.dao_emergency
    self.dao_emergency = new_dao_emergency
    log DaoEmergencyUpdated(previous_role=old_role, new_role=new_dao_emergency)


@external
def set_dao_agent(new_dao_agent: address):
    """
    @notice Rotate the DAO agent role.
    @param new_dao_agent New DAO agent admin
    """
    self._check_admin()
    assert new_dao_agent != empty(address), "Invalid dao_agent"

    old_role: address = self.dao_agent
    self.dao_agent = new_dao_agent
    log DaoAgentUpdated(previous_role=old_role, new_role=new_dao_agent)


################################################################
#                     ORACLE ADMIN WRAPPERS                    #
################################################################

@external
def set_header_verifier(_verifier: address):
    """
    @notice Forward header verifier updates to the oracle.
    @param _verifier Address of the header verifier
    """
    self._check_admin()
    extcall block_oracle.set_header_verifier(_verifier)


@external
def add_committer(_committer: address, _bump_threshold: bool = False):
    """
    @notice Add a committer to the oracle.
    @param _committer Address to authorize as committer
    @param _bump_threshold Whether to increment the oracle threshold
    """
    self._check_admin()
    extcall block_oracle.add_committer(_committer, _bump_threshold)


@external
def remove_committer(_committer: address):
    """
    @notice Remove a committer from the oracle.
    @param _committer Address to deauthorize as committer
    """
    self._check_admin()
    extcall block_oracle.remove_committer(_committer)


@external
def set_threshold(_new_threshold: uint256):
    """
    @notice Update oracle threshold.
    @param _new_threshold New oracle threshold
    """
    self._check_admin()
    extcall block_oracle.set_threshold(_new_threshold)


@external
def admin_apply_block(_block_number: uint256, _block_hash: bytes32):
    """
    @notice Apply a blockhash directly through the oracle owner path.
    @param _block_number Block number to confirm
    @param _block_hash Block hash to store
    """
    self._check_admin()
    extcall block_oracle.admin_apply_block(_block_number, _block_hash)


@external
def transfer_block_oracle_ownership(_new_owner: address):
    """
    @notice Transfer the bound oracle ownership away from this proxy.
    @param _new_owner New oracle owner
    """
    self._check_admin()
    extcall block_oracle.transfer_ownership(_new_owner)
