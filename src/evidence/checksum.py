"""
src/evidence/checksum.py — SHA-256 Checksum Sealing & Calculation Engine

Layer 3: Evidence & Verification Infrastructure
"""
import hashlib
from typing import Any

from src.evidence.canonical_json import encode_canonical_utf8


def hash_bytes_sha256(data: bytes) -> bytes:
    """Returns raw 32-byte SHA-256 digest of input binary data."""
    return hashlib.sha256(data).digest()


def calculate_png_hash_hex(png_bytes: bytes) -> str:
    """Calculates 64-character hex SHA-256 hash of PNG image stream."""
    return hashlib.sha256(png_bytes).hexdigest().lower()


def calculate_sealed_checksum(png_bytes: bytes, session_json_dict: dict[str, Any]) -> str:
    """
    Calculates the combined sealed SHA-256 checksum for a SessionBundle.
    
    Algorithm:
      1. Hash_1 = SHA256(png_bytes)               [32 raw bytes digest]
      2. Hash_2 = SHA256(Canonical JSON Payload)  [32 raw bytes digest, EXCLUDING 'checksum' key]
      3. Sealed_Checksum = SHA256(Hash_1 + Hash_2).hexdigest() [64-character hex]
    """
    # Exclude 'checksum' key if present in payload to prevent circular hashing
    payload_dict = {k: v for k, v in session_json_dict.items() if k != "checksum"}

    # Step 1: Raw SHA-256 of PNG bytes
    hash_1_raw = hash_bytes_sha256(png_bytes)

    # Step 2: Raw SHA-256 of Canonical JSON UTF-8 bytes
    canonical_utf8_bytes = encode_canonical_utf8(payload_dict)
    hash_2_raw = hash_bytes_sha256(canonical_utf8_bytes)

    # Step 3: Combined SHA-256 checksum
    combined_hasher = hashlib.sha256()
    combined_hasher.update(hash_1_raw)
    combined_hasher.update(hash_2_raw)

    return combined_hasher.hexdigest().lower()
