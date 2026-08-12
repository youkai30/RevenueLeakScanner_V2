"""
src/evidence/canonical_json.py — Deterministic Canonical JSON Serialization Engine

Layer 3: Evidence & Verification Infrastructure
"""
import json
from typing import Any


def _normalize_floats(obj: Any) -> Any:
    """Recursively rounds floating point numbers to 4 decimal places for cross-platform determinism."""
    if isinstance(obj, float):
        return round(obj, 4)
    if isinstance(obj, dict):
        return {k: _normalize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_floats(item) for item in obj]
    return obj


def canonicalize_json_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Applies float normalization and cleans data structure prior to serialization."""
    return _normalize_floats(data)  # type: ignore[no-any-return]


def dumps_canonical(data: dict[str, Any]) -> str:
    """
    Serializes a dictionary into a deterministic Canonical JSON string.
    
    Rules:
      1. Key Sorting: sort_keys=True
      2. Compact Whitespace: separators=(',', ':')
      3. Character Encoding: ensure_ascii=False (UTF-8)
      4. Float Normalization: Rounded to 4 decimal places
    """
    normalized_data = canonicalize_json_dict(data)
    return json.dumps(
        normalized_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def encode_canonical_utf8(data: dict[str, Any]) -> bytes:
    """Returns exact UTF-8 byte stream of canonicalized JSON dictionary."""
    return dumps_canonical(data).encode("utf-8")
