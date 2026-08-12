"""
src/evidence/session_storage.py — Write-Once Session Storage Engine

Layer 3: Evidence Storage Infrastructure
"""
import json
import os
import stat
from pathlib import Path
from uuid import UUID

from src.config import SESSIONS_DIR
from src.evidence.canonical_json import dumps_canonical, encode_canonical_utf8
from src.evidence.checksum import calculate_sealed_checksum
from src.evidence.models import SessionBundle
from src.exceptions import (
    ChecksumMismatchException,
    EvidenceTamperedException,
    InvalidBundleException,
    SessionExistsException,
    SessionNotFoundException,
)


class SessionStorage:
    """
    Enforces Write-Once physical disk storage and verification for Session Bundles.
    Contains NO update_bundle(), overwrite_bundle(), or upsert_bundle() methods.
    """

    def __init__(self, base_storage_dir: Path | None = None) -> None:
        self.base_dir = base_storage_dir or SESSIONS_DIR

    def get_session_dir(self, domain: str, session_id: UUID | str) -> Path:
        """Returns physical directory path for a specific domain session."""
        return self.base_dir / domain / str(session_id)

    def save_new_bundle(
        self,
        domain: str,
        session_id: UUID | str,
        png_bytes: bytes,
        session_bundle_dict: dict,
        all_pngs: dict[str, bytes] | None = None,
    ) -> SessionBundle:
        """
        Atomically saves a new Session Bundle to disk.
        Raises SessionExistsException if session directory or bundle already exists.
        """
        session_str = str(session_id)
        session_dir = self.get_session_dir(domain, session_str)

        if session_dir.exists():
            raise SessionExistsException(
                f"Session directory already exists: '{session_dir}'. Duplicate write rejected."
            )

        # Calculate sealed checksum before writing
        sealed_checksum = calculate_sealed_checksum(png_bytes, session_bundle_dict)

        # Inject final checksum into dictionary payload
        bundle_dict = dict(session_bundle_dict)
        bundle_dict["checksum"] = sealed_checksum

        # Validate complete payload against SessionBundle Pydantic schema
        try:
            bundle_obj = SessionBundle.model_validate(bundle_dict)
        except Exception as exc:
            raise InvalidBundleException(f"SessionBundle schema validation failed: {exc}") from exc

        # Create session directory atomically
        temp_dir = self.base_dir / domain / f"temp_{session_str}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            png_file = temp_dir / f"session_{session_str}.png"
            json_file = temp_dir / f"session_{session_str}.json"
            checksum_file = temp_dir / f"session_{session_str}.checksum"

            # Write PNG binary asset
            with open(png_file, "wb") as f:
                f.write(png_bytes)

            # Write all individual PNG files
            if all_pngs:
                for fname, fbytes in all_pngs.items():
                    with open(temp_dir / fname, "wb") as f:
                        f.write(fbytes)

            # Write Canonical JSON sidecar
            canonical_json_str = dumps_canonical(bundle_dict)
            with open(json_file, "w", encoding="utf-8") as f:
                f.write(canonical_json_str)

            # Write Checksum signature file
            with open(checksum_file, "w", encoding="utf-8") as f:
                f.write(sealed_checksum)

            # Atomic directory rename
            temp_dir.rename(session_dir)

            # Apply Windows/OS Read-Only Safeguard on all written files
            files_to_chmod = [
                session_dir / f"session_{session_str}.png",
                session_dir / f"session_{session_str}.json",
                session_dir / f"session_{session_str}.checksum",
            ]
            if all_pngs:
                for fname in all_pngs.keys():
                    files_to_chmod.append(session_dir / fname)

            for path in files_to_chmod:
                try:
                    os.chmod(path, stat.S_IREAD)
                except Exception:
                    pass  # Non-fatal safeguard on platforms with restricted permissions

            return bundle_obj

        except Exception as exc:
            # Clean up temp directory on failure
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise exc

    def get_bundle(self, domain: str, session_id: UUID | str) -> SessionBundle:
        """
        Loads and verifies a Session Bundle from disk.
        Executes full read-time verification checks.
        """
        session_str = str(session_id)
        session_dir = self.get_session_dir(domain, session_str)

        if not session_dir.exists():
            raise SessionNotFoundException(f"Session bundle not found for ID: {session_str}")

        png_path = session_dir / f"session_{session_str}.png"
        json_path = session_dir / f"session_{session_str}.json"
        checksum_path = session_dir / f"session_{session_str}.checksum"

        if not png_path.exists() or not json_path.exists() or not checksum_path.exists():
            raise InvalidBundleException(f"Missing required session bundle files inside: {session_dir}")

        # Read artifacts
        with open(png_path, "rb") as f:
            png_bytes = f.read()

        with open(json_path, "r", encoding="utf-8") as f:
            try:
                bundle_dict = json.load(f)
            except Exception as exc:
                raise InvalidBundleException(f"Corrupted JSON sidecar file: {json_path}") from exc

        with open(checksum_path, "r", encoding="utf-8") as f:
            stored_checksum = f.read().strip().lower()

        # Read-Time Integrity Assertions
        calculated_checksum = calculate_sealed_checksum(png_bytes, bundle_dict)

        if stored_checksum != calculated_checksum:
            raise ChecksumMismatchException(
                f"Checksum mismatch! Stored: '{stored_checksum}', Calculated: '{calculated_checksum}'"
            )

        if bundle_dict.get("checksum", "").lower() != calculated_checksum:
            raise EvidenceTamperedException("JSON internal checksum field has been tampered with.")

        # Pydantic schema validation
        try:
            return SessionBundle.model_validate(bundle_dict)
        except Exception as exc:
            raise InvalidBundleException(f"SessionBundle validation failed at read time: {exc}") from exc
