class ExecutorOptions:
    """Helper for building LayerZero executor options"""

    # Constants from the contract
    WORKER_ID = 1
    TYPE_3 = bytes([0x00, 0x03])

    # Option types
    OPTION_TYPE_LZRECEIVE = 1
    OPTION_TYPE_NATIVE_DROP = 2
    OPTION_TYPE_LZCOMPOSE = 3
    OPTION_TYPE_ORDERED_EXECUTION = 4
    OPTION_TYPE_LZREAD = 5

    @staticmethod
    def new_options() -> bytes:
        """Start new type 3 options"""
        return ExecutorOptions.TYPE_3

    @staticmethod
    def add_executor_option(options: bytes, option_type: int, option_data: bytes) -> bytes:
        """Add an executor option to existing options"""
        return (
            options
            + bytes([ExecutorOptions.WORKER_ID])  # worker id
            + len(option_data + bytes([option_type])).to_bytes(2, "big")  # size
            + bytes([option_type])  # option type
            + option_data  # option data
        )

    @staticmethod
    def encode_lz_receive(gas: int, value: int = 0) -> bytes:
        """
        Encode LZ receive option
        @param gas Gas limit for lzReceive
        @param value Optional native value
        """
        if value == 0:
            return gas.to_bytes(16, "big")  # 128 bits
        return gas.to_bytes(16, "big") + value.to_bytes(16, "big")

    @staticmethod
    def encode_native_drop(amount: int, receiver: bytes) -> bytes:
        """
        Encode native drop option
        @param amount Amount of native tokens
        @param receiver Receiver address as bytes32
        """
        assert len(receiver) == 32, "Receiver must be bytes32"
        return amount.to_bytes(16, "big") + receiver

    @staticmethod
    def encode_lz_compose(index: int, gas: int, value: int = 0) -> bytes:
        """
        Encode LZ compose option
        @param index Compose index
        @param gas Gas limit
        @param value Optional native value
        """
        if value == 0:
            return index.to_bytes(2, "big") + gas.to_bytes(16, "big")
        return index.to_bytes(2, "big") + gas.to_bytes(16, "big") + value.to_bytes(16, "big")

    @staticmethod
    def add_lz_receive_option(options: bytes, gas: int, value: int = 0) -> bytes:
        """Add LZ receive option to existing options"""
        option_data = ExecutorOptions.encode_lz_receive(gas, value)
        return ExecutorOptions.add_executor_option(
            options, ExecutorOptions.OPTION_TYPE_LZRECEIVE, option_data
        )

    @staticmethod
    def add_native_drop_option(options: bytes, amount: int, receiver: bytes) -> bytes:
        """Add native drop option to existing options"""
        option_data = ExecutorOptions.encode_native_drop(amount, receiver)
        return ExecutorOptions.add_executor_option(
            options, ExecutorOptions.OPTION_TYPE_NATIVE_DROP, option_data
        )


def build_default_options(gas: int = 60000) -> bytes:
    """Build default options with LZ receive gas"""
    options = ExecutorOptions.new_options()  # type 3
    return ExecutorOptions.add_lz_receive_option(options, gas)


def test_executor_options():
    # Check vanilla 60k gas option matches docs
    options = build_default_options(60000)
    assert options.hex() == "0003010011010000000000000000000000000000ea60"
    print(f"Default options: 0x{options.hex()}")

    # Test with different gas
    options_100k = build_default_options(100000)
    print(f"100k gas options: 0x{options_100k.hex()}")

    # Test multiple options
    options = ExecutorOptions.new_options()
    options = ExecutorOptions.add_lz_receive_option(options, 60000)
    options = ExecutorOptions.add_native_drop_option(
        options, amount=1000000, receiver=bytes.fromhex("00" * 32)
    )
    print(f"Options with native drop: 0x{options.hex()}")


def test_contract_options(lz_contract):
    # Test contract options
    options_python = build_default_options(60000)
    print(f"Python options: 0x{options_python.hex()}")
    options_contract = lz_contract.eval(f"self._build_lz_receive_option({60000})")
    print(f"Contract options: 0x{options_contract.hex()}")
    assert options_python == options_contract
