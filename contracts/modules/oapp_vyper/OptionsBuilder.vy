# pragma version 0.4.1

"""
@license Copyright (c) Curve.Fi, 2025 - all rights reserved

@author curve.fi

@custom:security security@curve.fi
"""

# Vyper-specific constants
from . import VyperConstants as constants


################################################################
#                           CONSTANTS                          #
################################################################

MAX_OPTIONS_TOTAL_SIZE: constant(uint256) = constants.MAX_OPTIONS_TOTAL_SIZE
MAX_OPTION_SINGLE_SIZE: constant(uint256) = constants.MAX_OPTION_SINGLE_SIZE

# LayerZero protocol constants
TYPE_1: constant(uint16) = 1
TYPE_2: constant(uint16) = 2
TYPE_3: constant(uint16) = 3

EXECUTOR_WORKER_ID: constant(uint8) = 1
DVN_WORKER_ID: constant(uint8) = 2

# Option types
OPTION_TYPE_LZRECEIVE: constant(uint8) = 1
OPTION_TYPE_NATIVE_DROP: constant(uint8) = 2
OPTION_TYPE_LZCOMPOSE: constant(uint8) = 3
OPTION_TYPE_ORDERED_EXECUTION: constant(uint8) = 4
OPTION_TYPE_LZREAD: constant(uint8) = 5

# DVN option types
OPTION_TYPE_DVN: constant(uint8) = 10
OPTION_TYPE_DVN_PRECRIME: constant(uint8) = 1


################################################################
#                        OptionsBuilder                        #
################################################################
# Includes partial implementation of ExecutorOptions.sol

@internal
@pure
def newOptions() -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @notice Creates a new options container with type 3.
    @return options The newly created options container.
    """
    options: Bytes[MAX_OPTIONS_TOTAL_SIZE] = concat(convert(TYPE_3, bytes2), b"")

    return options


@internal
@pure
def addExecutorOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE],
    _optionType: uint8,
    _option: Bytes[MAX_OPTION_SINGLE_SIZE],
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds an executor option to the existing options.
    @param _options The existing options container.
    @param _optionType The type of the executor option.
    @param _option The encoded data for the executor option.
    @return options The updated options container.
    """
    assert convert(slice(_options, 0, 2), uint16) == TYPE_3, "OApp: invalid option type"
    assert (len(_options) + len(_option) <= MAX_OPTIONS_TOTAL_SIZE), "OApp: options size exceeded"

    return concat(
        abi_decode(
            abi_encode(_options), (Bytes[MAX_OPTIONS_TOTAL_SIZE - MAX_OPTION_SINGLE_SIZE - 4])
        ),  # -4 for header
        convert(EXECUTOR_WORKER_ID, bytes1),
        convert(convert(len(_option) + 1, uint16), bytes2),  # +1 for optionType
        convert(_optionType, bytes1),
        _option,
    )


@internal
@pure
def addExecutorLzReceiveOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE], _gas: uint128, _value: uint128
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @notice Adds an executor LZ receive option to the existing options.
    @param _options The existing options container.
    @param _gas The gasLimit used on the lzReceive() function in the OApp.
    @param _value The msg.value passed to the lzReceive() function in the OApp.
    @return options The updated options container.
    @dev When multiples of this option are added, they are summed by the executor
    eg. if (_gas: 200k, and _value: 1 ether) AND (_gas: 100k, _value: 0.5 ether) are sent in an option to the LayerZeroEndpoint,
    that becomes (300k, 1.5 ether) when the message is executed on the remote lzReceive() function.

    @dev Vyper-specific: ExecutorOptions.encodeLzReceiveOption is inlined here.
    OnlyType3 is not checked here as it is checked in addExecutorOption.
    """
    option: Bytes[MAX_OPTION_SINGLE_SIZE] = b""
    gas_bytes: bytes16 = convert(_gas, bytes16)

    if _value > 0:
        value_bytes: bytes16 = convert(_value, bytes16)
        option = concat(gas_bytes, value_bytes)
    else:
        option = concat(gas_bytes, b"")  # bytes -> Bytes

    return self.addExecutorOption(_options, OPTION_TYPE_LZRECEIVE, option)


@internal
@pure
def addExecutorNativeDropOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE], _amount: uint128, _receiver: bytes32
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds an executor native drop option to the existing options.
    @param _options The existing options container.
    @param _amount The amount for the native value that is airdropped to the 'receiver'.
    @param _receiver The receiver address for the native drop option.
    @return options The updated options container.
    @dev When multiples of this option are added, they are summed by the executor on the remote chain.
    """
    option: Bytes[MAX_OPTION_SINGLE_SIZE] = concat(convert(_amount, bytes16), _receiver)

    return self.addExecutorOption(_options, OPTION_TYPE_NATIVE_DROP, option)


@internal
@pure
def addExecutorLzComposeOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE],
    _index: uint16,
    _gas: uint128,
    _value: uint128,
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds an executor LZ compose option to the existing options.
    @param _options The existing options container.
    @param _index The index for the lzCompose() function call.
    @param _gas The gasLimit for the lzCompose() function call.
    @param _value The msg.value for the lzCompose() function call.
    @return options The updated options container.
    @dev When multiples of this option are added, they are summed PER index by the executor on the remote chain.
    @dev If the OApp sends N lzCompose calls on the remote, you must provide N incremented indexes starting with 0.
    @dev ie. When your remote OApp composes (N = 3) messages, you must set this option for index 0,1,2
    """
    option: Bytes[MAX_OPTION_SINGLE_SIZE] = b""

    index_bytes: bytes2 = convert(_index, bytes2)
    gas_bytes: bytes16 = convert(_gas, bytes16)

    if _value > 0:
        value_bytes: bytes16 = convert(_value, bytes16)
        option = concat(index_bytes, gas_bytes, value_bytes)
    else:
        option = concat(index_bytes, gas_bytes)

    return self.addExecutorOption(_options, OPTION_TYPE_LZCOMPOSE, option)


@internal
@pure
def addExecutorOrderedExecutionOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE],
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds an executor ordered execution option to the existing options.
    @param _options The existing options container.
    @return options The updated options container.
    """
    return self.addExecutorOption(_options, OPTION_TYPE_ORDERED_EXECUTION, b"")


@internal
@pure
def addExecutorLzReadOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE], _gas: uint128, _size: uint32, _value: uint128
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds an executor LZ read option to the existing options.
    @param _options The existing options container.
    @param _gas The gasLimit for the lzRead() function call.
    @param _size The size of the lzRead() function call.
    @param _value The msg.value for the lzRead return function call.
    @return options The updated options container.
    """
    option: Bytes[MAX_OPTION_SINGLE_SIZE] = b""

    gas_bytes: bytes16 = convert(_gas, bytes16)
    size_bytes: bytes4 = convert(_size, bytes4)

    if _value > 0:
        value_bytes: bytes16 = convert(_value, bytes16)
        option = concat(gas_bytes, size_bytes, value_bytes)
    else:
        option = concat(gas_bytes, size_bytes)

    return self.addExecutorOption(_options, OPTION_TYPE_LZREAD, option)


@internal
@pure
def addDVNOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE],
    _dvnIdx: uint8,
    _optionType: uint8,
    _option: Bytes[MAX_OPTION_SINGLE_SIZE],
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds a DVN option to the existing options.
    @param _options The existing options container.
    @param _dvnIdx The DVN index for the DVN option.
    @param _optionType The type of the DVN option.
    @param _option The encoded data for the DVN option.
    @return options The updated options container.
    """
    assert convert(slice(_options, 0, 2), uint16) == TYPE_3, "OApp: invalid option type"
    assert (len(_options) + len(_option) <= MAX_OPTIONS_TOTAL_SIZE), "OApp: options size exceeded"

    return concat(
        abi_decode(
            abi_encode(_options), (Bytes[MAX_OPTIONS_TOTAL_SIZE - MAX_OPTION_SINGLE_SIZE - 5])
        ),  # -5 for header
        convert(DVN_WORKER_ID, bytes1),
        convert(convert(len(_option) + 2, uint16), bytes2),  # +2 for optionType and dvnIdx
        convert(_dvnIdx, bytes1),
        convert(_optionType, bytes1),
        _option,
    )


@internal
@pure
def addDVNPreCrimeOption(
    _options: Bytes[MAX_OPTIONS_TOTAL_SIZE], _dvnIdx: uint8
) -> Bytes[MAX_OPTIONS_TOTAL_SIZE]:
    """
    @dev Adds a DVN pre-crime option to the existing options.
    @param _options The existing options container.
    @param _dvnIdx The DVN index for the pre-crime option.
    @return options The updated options container.
    """
    return self.addDVNOption(_options, _dvnIdx, OPTION_TYPE_DVN_PRECRIME, b"")
