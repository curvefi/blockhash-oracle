from cryptography.fernet import Fernet
import keyring
import base64
from getpass import getpass

KEYCHAIN_SERVICE = "blockhash_oracle_deployment"
KEYCHAIN_USERNAME = "web3_deployer"


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


def encrypt_private_key(private_key: str) -> str:
    """
    Encrypt private key using key from keychain
    Returns the encrypted key that can be stored in .env
    """
    # Generate or get encryption key
    key = get_encryption_key()
    f = Fernet(key)

    # Encrypt the private key
    encrypted_key = f.encrypt(private_key.encode())
    return base64.b64encode(encrypted_key).decode()


def decrypt_private_key(encrypted_key: str) -> str:
    """
    Decrypt private key using key from keychain
    """
    # Get encryption key from keychain
    key = get_encryption_key()
    f = Fernet(key)

    # Decrypt the private key
    encrypted_bytes = base64.b64decode(encrypted_key.encode())
    decrypted_key = f.decrypt(encrypted_bytes)
    return decrypted_key.decode()


def setup_encrypted_key():
    """
    Interactive function to set up encrypted private key
    Returns the encrypted key to be stored in .env
    """
    print("Enter your private key (it will not be displayed):")
    private_key = getpass()
    return encrypt_private_key(private_key)


def get_web3_account(encrypted_key: str):
    """
    Get Web3 account from encrypted private key
    """
    from eth_account import Account

    private_key = decrypt_private_key(encrypted_key)
    return Account.from_key(private_key)


if __name__ == "__main__":
    # If run directly, help user set up encrypted key
    try:
        encrypted = setup_encrypted_key()
        print("\nAdd this to your .env file as ENCRYPTED_PRIVATE_KEY:")
        print(encrypted)
        # now decrypt the key
        decrypted = decrypt_private_key(encrypted)
        # print("\nDecrypted key:")
        # print(decrypted)
    except Exception as e:
        print(f"Error: {e}")
