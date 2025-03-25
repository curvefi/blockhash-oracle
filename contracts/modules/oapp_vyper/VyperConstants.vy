# pragma version 0.4.1

"""
@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@notice Vyper does not allow truly dynamic byte arrays, and requires constants to cap the size of the array.
This file contains such constants for the LayerZero OApp.

@dev IMPORTANT: Tune these down as much as possible according to intended use case to save on gas.

@author curve.fi

@custom:security security@curve.fi
"""

# Options size limits
MAX_OPTIONS_TOTAL_SIZE: constant(uint256) = 256
MAX_OPTION_SINGLE_SIZE: constant(uint256) = 64

# Message size limits
MAX_MESSAGE_SIZE: constant(uint256) = 512
MAX_EXTRA_DATA_SIZE: constant(uint256) = 64

# ReadCmdCodecV1 limits
MAX_CALLDATA_SIZE: constant(uint256) = 128

# ConfigUtils limits
MAX_DVNS: constant(uint256) = 16
MAX_CONFIG_ITEMS: constant(uint256) = 32
