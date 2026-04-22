"""
BioHash - String hashing utilities for the bio RAG server.

This module provides various hashing functions for string inputs,
supporting multiple hash algorithms and output formats.
"""

import hashlib
import hmac
import secrets
from typing import Optional


def md5_hash(text: str, encoding: str = "utf-8") -> str:
    """
    Generate MD5 hash for a string input.

    Args:
        text: Input string to hash
        encoding: String encoding (default: utf-8)

    Returns:
        MD5 hash as hexadecimal string
    """
    return hashlib.md5(text.encode(encoding)).hexdigest()


def sha1_hash(text: str, encoding: str = "utf-8") -> str:
    """
    Generate SHA1 hash for a string input.

    Args:
        text: Input string to hash
        encoding: String encoding (default: utf-8)

    Returns:
        SHA1 hash as hexadecimal string
    """
    return hashlib.sha1(text.encode(encoding)).hexdigest()


def sha256_hash(text: str, encoding: str = "utf-8") -> str:
    """
    Generate SHA256 hash for a string input.

    Args:
        text: Input string to hash
        encoding: String encoding (default: utf-8)

    Returns:
        SHA256 hash as hexadecimal string
    """
    return hashlib.sha256(text.encode(encoding)).hexdigest()


def sha512_hash(text: str, encoding: str = "utf-8") -> str:
    """
    Generate SHA512 hash for a string input.

    Args:
        text: Input string to hash
        encoding: String encoding (default: utf-8)

    Returns:
        SHA512 hash as hexadecimal string
    """
    return hashlib.sha512(text.encode(encoding)).hexdigest()


def blake2b_hash(text: str, digest_size: int = 64, encoding: str = "utf-8") -> str:
    """
    Generate BLAKE2b hash for a string input.

    Args:
        text: Input string to hash
        digest_size: Size of the digest in bytes (1-64, default: 64)
        encoding: String encoding (default: utf-8)

    Returns:
        BLAKE2b hash as hexadecimal string
    """
    return hashlib.blake2b(text.encode(encoding), digest_size=digest_size).hexdigest()


def hmac_hash(
    text: str,
    key: Optional[str] = None,
    algorithm: str = "sha256",
    encoding: str = "utf-8",
) -> str:
    """
    Generate HMAC hash for a string input with optional key.

    Args:
        text: Input string to hash
        key: Secret key for HMAC (if None, a random key will be generated)
        algorithm: Hash algorithm to use (sha1, sha256, sha512, etc.)
        encoding: String encoding (default: utf-8)

    Returns:
        HMAC hash as hexadecimal string
    """
    if key is None:
        key = secrets.token_hex(32)

    hash_func = getattr(hashlib, algorithm.lower())
    return hmac.new(key.encode(encoding), text.encode(encoding), hash_func).hexdigest()


def hash_string(
    text: str, algorithm: str = "sha256", encoding: str = "utf-8", **kwargs
) -> str:
    """
    Generate hash for a string input using specified algorithm.

    Args:
        text: Input string to hash
        algorithm: Hash algorithm (md5, sha1, sha256, sha512, blake2b, hmac)
        encoding: String encoding (default: utf-8)
        **kwargs: Additional arguments for specific algorithms

    Returns:
        Hash as hexadecimal string

    Raises:
        ValueError: If algorithm is not supported
    """
    algorithm = algorithm.lower()

    if algorithm == "md5":
        return md5_hash(text, encoding)
    elif algorithm == "sha1":
        return sha1_hash(text, encoding)
    elif algorithm == "sha256":
        return sha256_hash(text, encoding)
    elif algorithm == "sha512":
        return sha512_hash(text, encoding)
    elif algorithm == "blake2b":
        digest_size = kwargs.get("digest_size", 64)
        return blake2b_hash(text, digest_size, encoding)
    elif algorithm == "hmac":
        key = kwargs.get("key")
        hmac_algorithm = kwargs.get("hmac_algorithm", "sha256")
        return hmac_hash(text, key, hmac_algorithm, encoding)
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def hash_with_salt(
    text: str,
    salt: Optional[str] = None,
    algorithm: str = "sha256",
    encoding: str = "utf-8",
) -> str:
    """
    Generate hash for a string input with salt.

    Args:
        text: Input string to hash
        salt: Salt string (if None, a random salt will be generated)
        algorithm: Hash algorithm to use
        encoding: String encoding (default: utf-8)

    Returns:
        Hash as hexadecimal string
    """
    if salt is None:
        salt = secrets.token_hex(16)

    salted_text = f"{salt}:{text}"
    return hash_string(salted_text, algorithm, encoding)


def hash_file_content(
    file_path: str, algorithm: str = "sha256", chunk_size: int = 8192
) -> str:
    """
    Generate hash for file content.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use
        chunk_size: Size of chunks to read file in

    Returns:
        Hash as hexadecimal string
    """
    hash_func = getattr(hashlib, algorithm.lower())()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def verify_hash(
    text: str, expected_hash: str, algorithm: str = "sha256", encoding: str = "utf-8"
) -> bool:
    """
    Verify if a string matches an expected hash.

    Args:
        text: Input string to verify
        expected_hash: Expected hash value
        algorithm: Hash algorithm used
        encoding: String encoding (default: utf-8)

    Returns:
        True if hash matches, False otherwise
    """
    actual_hash = hash_string(text, algorithm, encoding)
    return actual_hash == expected_hash


# Convenience functions for common use cases
def quick_hash(text: str) -> str:
    """Generate a quick SHA256 hash for a string."""
    return sha256_hash(text)


def secure_hash(text: str) -> str:
    """Generate a secure hash with salt for a string."""
    return hash_with_salt(text, algorithm="sha512")


def short_hash(text: str, length: int = 8) -> str:
    """Generate a short hash (first N characters) for a string."""
    full_hash = sha256_hash(text)
    return full_hash[:length]


# Example usage and testing
if __name__ == "__main__":
    # Test the hash functions
    test_string = "Hello, World!"

    print(f"Original string: {test_string}")
    print(f"MD5: {md5_hash(test_string)}")
    print(f"SHA1: {sha1_hash(test_string)}")
    print(f"SHA256: {sha256_hash(test_string)}")
    print(f"SHA512: {sha512_hash(test_string)}")
    print(f"BLAKE2b: {blake2b_hash(test_string)}")
    print(f"HMAC: {hmac_hash(test_string)}")
    print(f"With salt: {hash_with_salt(test_string)}")
    print(f"Quick hash: {quick_hash(test_string)}")
    print(f"Secure hash: {secure_hash(test_string)}")
    print(f"Short hash: {short_hash(test_string, 12)}")

    # Test verification
    hash_value = sha256_hash(test_string)
    print(f"Verification: {verify_hash(test_string, hash_value)}")
