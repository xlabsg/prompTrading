"""Encryption utilities for trading API credentials."""

import os
from cryptography.fernet import Fernet


def get_encryption_key() -> bytes:
    """
    Get encryption key from environment variable.
    
    If not set, generates a key for development (NOT for production use).
    
    Returns:
        Encryption key as bytes
    """
    key = os.getenv("TRADING_API_ENCRYPTION_KEY")
    if not key:
        # Generate a key for development
        generated_key = Fernet.generate_key().decode()
        print(f"⚠️  WARNING: Generated encryption key for development: {generated_key}")
        print("   Set TRADING_API_ENCRYPTION_KEY environment variable for production")
        key = generated_key
    return key.encode()


# Global encryption key
ENCRYPTION_KEY = get_encryption_key()
_fernet = Fernet(ENCRYPTION_KEY)


def encrypt_credential(value: str) -> str:
    """
    Encrypt a credential for storage.
    
    Args:
        value: Plain text credential
        
    Returns:
        Encrypted credential as string
    """
    if not value:
        return ""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_credential(encrypted: str) -> str:
    """
    Decrypt a stored credential.
    
    Args:
        encrypted: Encrypted credential
        
    Returns:
        Plain text credential
    """
    if not encrypted:
        return ""
    return _fernet.decrypt(encrypted.encode()).decode()
