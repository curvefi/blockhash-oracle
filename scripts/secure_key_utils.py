from cryptography.fernet import Fernet
import keyring
import base64
from getpass import getpass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os

KEYCHAIN_SERVICE = "web3_credentials"
KEYCHAIN_USERNAME = "deployer"
SALT_LENGTH = 16  # for PBKDF2
PBKDF2HMAC_ITERATIONS = 5_000_000  # ~2s on m2pro


def generate_and_store_key():
    """Generate encryption key and store it in keychain"""
    key = Fernet.generate_key()
    keyring.set_password(KEYCHAIN_SERVICE, f"{KEYCHAIN_USERNAME}_key", key.decode())
    return key


def get_encryption_key():
    """Retrieve encryption key from keychain"""
    key = keyring.get_password(KEYCHAIN_SERVICE, f"{KEYCHAIN_USERNAME}_key")
    if not key:
        key = generate_and_store_key()
    return key.encode() if isinstance(key, str) else key


def derive_key_from_password(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """
    Derive a key from password using PBKDF2
    Returns (key, salt) tuple
    """
    if salt is None:
        salt = os.urandom(SALT_LENGTH)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2HMAC_ITERATIONS,
    )
    key = base64.b64encode(kdf.derive(password.encode()))
    return key, salt


def encrypt_private_key(private_key: str, password: str) -> str:
    """
    Encrypt private key using both keychain key and password
    Returns the encrypted key that can be stored in .env
    """
    # First layer: password-based encryption
    password_key, salt = derive_key_from_password(password)
    f1 = Fernet(password_key)
    first_layer = f1.encrypt(private_key.encode())

    # Second layer: keychain-based encryption
    keychain_key = get_encryption_key()
    f2 = Fernet(keychain_key)
    second_layer = f2.encrypt(first_layer)

    # Combine salt with encrypted data
    combined = salt + second_layer
    return base64.b64encode(combined).decode()


def decrypt_private_key(encrypted_key: str, password: str) -> str:
    """
    Decrypt private key using both keychain key and password
    """
    # Decode the combined data
    encrypted_data = base64.b64decode(encrypted_key.encode())
    salt = encrypted_data[:SALT_LENGTH]
    encrypted_payload = encrypted_data[SALT_LENGTH:]

    # First layer: keychain-based decryption
    keychain_key = get_encryption_key()
    f2 = Fernet(keychain_key)
    first_layer = f2.decrypt(encrypted_payload)

    # Second layer: password-based decryption
    password_key, _ = derive_key_from_password(password, salt)
    f1 = Fernet(password_key)
    decrypted_key = f1.decrypt(first_layer)

    return decrypted_key.decode()


def setup_encrypted_key():
    """
    Interactive function to set up encrypted private key
    Returns the encrypted key to be stored in .env
    """
    print("Enter your private key (it will not be displayed):")
    private_key = getpass()
    print("\nEnter a strong password for additional encryption:")
    password = getpass()
    print("Confirm password:")
    password_confirm = getpass()

    if password != password_confirm:
        raise ValueError("Passwords do not match!")

    return encrypt_private_key(private_key, password)


def get_web3_account(encrypted_key: str, password: str):
    """
    Get Web3 account from encrypted private key
    """
    from eth_account import Account

    private_key = decrypt_private_key(encrypted_key, password)
    return Account.from_key(private_key)


def test_pbkdf2_time(iterations):
    import time

    salt = os.urandom(16)
    start = time.time()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    kdf.derive(b"test password")

    duration = time.time() - start
    print(f"Iterations: {iterations:,}, Time: {duration:.2f}s")
    return duration


if __name__ == "__main__":
    ## Some preliminary benchmark tests
    # for i in [100_000, 480_000, 1_000_000, 2_000_000, 5_000_000]:
    #     test_pbkdf2_time(i)

    # If run directly, help user set up encrypted key
    try:
        encrypted = setup_encrypted_key()
        print("\nAdd this to your .env file as ENCRYPTED_PRIVATE_KEY:")
        print(encrypted)

        # Verify decryption
        print("\nVerifying decryption - enter your password:")
        verify_password = getpass()
        try:
            decrypted = decrypt_private_key(encrypted, verify_password)
            print("\nDecryption successful! Your key is secure.")
        except Exception as e:
            print("\nDecryption failed. Please ensure you remember your password!")
            print(e)
    except Exception as e:
        print(f"Error: {e}")
