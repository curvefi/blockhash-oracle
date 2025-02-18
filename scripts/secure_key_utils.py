from eth_account import Account
import keyring
import base58
import json
from getpass import getpass
import sys
import time
from cryptography.fernet import Fernet

KEYCHAIN_SERVICE = "web3_credentials"
KEYCHAIN_USERNAME = "deployer"
DEFAULT_SCRYPT_ITERATIONS = 2**21  # m2pro: 2**20 is ~2s, 2**21 is ~4s etc


def get_keyring_key() -> bytes:
    """
    Get or generate Fernet encryption key from keyring.
    This key is used as an additional encryption layer.
    """
    key = keyring.get_password(KEYCHAIN_SERVICE, f"{KEYCHAIN_USERNAME}_key")
    if not key:
        # Generate a new Fernet key and store it in keyring as is
        key = Fernet.generate_key().decode()
        keyring.set_password(KEYCHAIN_SERVICE, f"{KEYCHAIN_USERNAME}_key", key)
    return key.encode()  # Return bytes for Fernet


def get_private_key() -> bytes:
    """
    Prompts for your secret: either a private key in hex or a mnemonic phrase.
    Returns the private key as bytes.
    If a mnemonic is provided (detected by spaces), derive the private key using the default path.
    """
    secret = getpass("Enter your secret (private key in hex OR mnemonic phrase): ").strip()
    # If the input has a space, assume it's a mnemonic
    if " " in secret:
        try:
            Account.enable_unaudited_hdwallet_features()
            account = Account.from_mnemonic(secret)
            print("Derived private key from mnemonic.")
            return account.key
        except Exception as e:
            print("Error deriving private key from mnemonic:", e)
            sys.exit(1)
    else:
        # Assume it's a hexadecimal private key string
        if secret.startswith("0x"):
            secret = secret[2:]
        try:
            return bytes.fromhex(secret)
        except Exception as e:
            print("Error parsing private key in hex:", e)
            sys.exit(1)


def encrypt_private_key(
    private_key: bytes, password: str, iterations: int = DEFAULT_SCRYPT_ITERATIONS
) -> str:
    """
    Encrypt private key using both keyring and eth_account's encryption:
    1. First layer: eth_account's scrypt encryption
    2. Second layer: Fernet encryption using keyring key
    Returns the encrypted key that can be stored in .env
    """
    # First layer: eth_account's encryption
    print(f"\nEncrypting with {iterations} scrypt iterations...")
    start_time = time.time()

    encrypted_data = Account.encrypt(private_key, password, kdf="scrypt", iterations=iterations)

    # Convert to string for Fernet encryption
    encrypted_str = json.dumps(encrypted_data, separators=(",", ":"))

    # Second layer: keyring-based encryption
    keyring_key = get_keyring_key()
    f = Fernet(keyring_key)
    final_encrypted = f.encrypt(encrypted_str.encode())

    encryption_time = time.time() - start_time
    print(f"Encryption took {encryption_time:.2f} seconds")

    # Encode as base58 for storage
    return base58.b58encode(final_encrypted).decode()


def decrypt_private_key(encrypted_combined: str, password: str) -> bytes:
    """
    Decrypt private key using both keyring and password:
    1. First layer: Fernet decryption using keyring key
    2. Second layer: eth_account's scrypt decryption
    """
    try:
        # Decode from base58
        encrypted_data = base58.b58decode(encrypted_combined)

        # First layer: keyring-based decryption
        keyring_key = get_keyring_key()
        f = Fernet(keyring_key)
        decrypted_str = f.decrypt(encrypted_data)

        # Parse the eth_account encrypted data
        encrypted_key = json.loads(decrypted_str)

        # Extract and display KDF parameters
        kdf_params = encrypted_key.get("crypto", {}).get("kdfparams", {})
        iterations = kdf_params.get("n", "unknown")
        print(f"\nDetected {iterations} scrypt iterations in the encrypted key")

        print("\nDecrypting...")
        start_time = time.time()

        # Second layer: eth_account's decryption
        private_key = Account.decrypt(encrypted_key, password)
        decryption_time = time.time() - start_time
        print(f"Decryption took {decryption_time:.2f} seconds")

        return private_key

    except Exception as e:
        print("Error decrypting the key:", e)
        sys.exit(1)


def setup_encrypted_key(iterations: int = DEFAULT_SCRYPT_ITERATIONS) -> str:
    """
    Interactive function to set up encrypted private key
    Returns the encrypted key to be stored in .env
    """
    private_key = get_private_key()
    acc_pre = Account.from_key(private_key)
    print(f"\nAccount address: {acc_pre.address}")
    print("\nEnter a strong password for encryption:")
    password = getpass()
    print("Confirm password:")
    password_confirm = getpass()

    if password != password_confirm:
        raise ValueError("Passwords do not match!")

    encrypted = encrypt_private_key(private_key, password, iterations)

    # Verify decryption
    print("\nVerifying decryption - enter your password:")
    verify_password = getpass()
    try:
        decrypted_key = decrypt_private_key(encrypted, verify_password)
        account = Account.from_key(decrypted_key)
        print(f"Decrypted account address: {account.address}")
        assert account.address == acc_pre.address
        print("\nDecryption successful! Your key is secure.")
    except Exception as e:
        print("\nDecryption verification failed. Please ensure you remember your password!")
        print(e)
        sys.exit(1)

    return encrypted


def get_web3_account(encrypted_key: str, password: str):
    """
    Get Web3 account from encrypted private key
    """
    private_key = decrypt_private_key(encrypted_key, password)
    return Account.from_key(private_key)


def benchmark_scrypt(iterations_list=None):
    """
    Benchmark scrypt encryption/decryption times with different iteration counts
    """
    if iterations_list is None:
        iterations_list = [n for n in range(14, 30)]

    # Generate a test private key
    test_key = Account.create().key
    test_password = "benchmark_password"

    print("\nBenchmarking scrypt encryption/decryption times:")
    print("Iterations | Encryption | Decryption | Total")
    print("-" * 45)

    for n in iterations_list:
        # Time encryption
        start_time = time.time()
        encrypted = Account.encrypt(test_key, test_password, kdf="scrypt", iterations=2**n)
        encrypt_time = time.time() - start_time

        # Time decryption
        start_time = time.time()
        Account.decrypt(encrypted, test_password)
        decrypt_time = time.time() - start_time

        total_time = encrypt_time + decrypt_time
        print(f"{n:10,d} | {encrypt_time:9.2f}s | {decrypt_time:9.2f}s | {total_time:5.2f}s")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        benchmark_scrypt()
    else:
        try:
            encrypted = setup_encrypted_key()
            print("\nAdd this to your .env file as ENCRYPTED_PRIVATE_KEY:")
            print(encrypted)
        except Exception as e:
            print(f"Error: {e}")
