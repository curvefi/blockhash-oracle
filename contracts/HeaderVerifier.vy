# pragma version 0.4.3
# pragma optimize gas

"""
@title Block Header Verifier

@notice Simple contract that makes use of rlp header decoder module and forwards
        decoded headers to an oracle contract. No security checks or logs.

@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

################################################################
#                          INTERFACES                          #
################################################################

interface IBlockOracle:
    def submit_block_header(block_header: bh_rlp.BlockHeader): nonpayable

################################################################
#                            MODULES                           #
################################################################

# Import RLP Block Header Decoder
from modules import BlockHeaderRLPDecoder as bh_rlp

exports: (bh_rlp.decode_block_header,)

################################################################
#                 PERMISSIONLESS FUNCTIONS                     #
################################################################

@external
def submit_block_header(_oracle_address: address, _encoded_header: Bytes[bh_rlp.BLOCK_HEADER_SIZE]):
    """
    @notice Submit a block header. If it's correct and blockhash is applied, store it.
    @param _oracle_address The address of the oracle contract
    @param _encoded_header The block header to submit
    """
    # Decode whatever is submitted
    decoded_header: bh_rlp.BlockHeader = bh_rlp._decode_block_header(_encoded_header)
    # Explicitly assert correctness (already done when decoding, double check)
    assert keccak256(_encoded_header) == decoded_header.block_hash, "Invalid header"
    # Submit decoded header to oracle
    extcall IBlockOracle(_oracle_address).submit_block_header(decoded_header)
