"""
tests/test_foundation.py — Comprehensive Test Suite for Phase A Foundation

Covers:
  - StoreRecord validation & normalization
  - BoundingBox & BoundingBoxMap validation
  - CommercialImpact validation
  - SessionBundle immutability & schema assertions
  - Canonical JSON determinism
  - SHA-256 Checksum sealing
  - Write-Once Storage API & duplicate session protection
  - Tamper detection (PNG, JSON, Checksum file modifications)
"""
import copy
import json
import pytest
from pydantic import ValidationError

from src.evidence.canonical_json import dumps_canonical, encode_canonical_utf8
from src.evidence.checksum import calculate_png_hash_hex, calculate_sealed_checksum
from src.evidence.models import (
    BoundingBox,
    BoundingBoxMap,
    CommercialImpact,
    Finding,
    SessionBundle,
    VisualEvidence,
)
from src.evidence.session_storage import SessionStorage
from src.exceptions import (
    ChecksumMismatchException,
    DomainValidationError,
    EvidenceTamperedException,
    InvalidBoundingBoxError,
    InvalidCommercialMetricsError,
    RevenueLeakScannerError,
    SessionExistsException,
    SessionNotFoundException,
)
from src.ingestion.store_loader import StoreRecord


# ---------------------------------------------------------------------------
# A. StoreRecord Validation Tests
# ---------------------------------------------------------------------------
def test_store_record_valid():
    rec = StoreRecord(domain="nativecos.com", base_url="https://nativecos.com")
    assert rec.domain == "nativecos.com"
    assert rec.base_url == "https://nativecos.com"


def test_store_record_normalization():
    rec = StoreRecord(domain="  HTTPS://TOMS.COM/products/shoe  ", base_url="  https://toms.com  ")
    assert rec.domain == "toms.com"
    assert rec.base_url == "https://toms.com"


def test_store_record_invalid_domain():
    with pytest.raises(DomainValidationError):
        StoreRecord(domain="invalid_domain_without_dot", base_url="https://valid.com")


def test_store_record_invalid_url():
    with pytest.raises(DomainValidationError):
        StoreRecord(domain="valid.com", base_url="ftp://invalid-scheme.com")


def test_store_record_immutability():
    rec = StoreRecord(domain="nativecos.com", base_url="https://nativecos.com")
    with pytest.raises(ValidationError):
        rec.domain = "other.com"  # Frozen check


# ---------------------------------------------------------------------------
# B. BoundingBox & BoundingBoxMap Tests
# ---------------------------------------------------------------------------
def test_bounding_box_valid():
    bb = BoundingBox(x=10.5, y=20.0, width=100.0, height=50.0)
    assert bb.x == 10.5
    assert bb.height == 50.0


def test_bounding_box_negative_rejected():
    with pytest.raises(InvalidBoundingBoxError):
        BoundingBox(x=-1.0, y=0.0, width=10.0, height=10.0)


def test_bounding_box_map_optional():
    bb_map = BoundingBoxMap(cta=BoundingBox(x=0.0, y=0.0, width=10.0, height=10.0))
    assert bb_map.cta is not None
    assert bb_map.buy_box is None


# ---------------------------------------------------------------------------
# C. CommercialImpact Tests
# ---------------------------------------------------------------------------
def test_commercial_impact_valid(valid_commercial_dict):
    ci = CommercialImpact.model_validate(valid_commercial_dict)
    assert ci.est_monthly_loss_usd == 24480.0
    assert ci.lead_priority == "HIGH"


def test_commercial_impact_invalid_priority(valid_commercial_dict):
    data = dict(valid_commercial_dict)
    data["lead_priority"] = "SUPER_HIGH"
    with pytest.raises(InvalidCommercialMetricsError):
        CommercialImpact.model_validate(data)


def test_commercial_impact_invalid_confidence(valid_commercial_dict):
    data = dict(valid_commercial_dict)
    data["confidence_score"] = 1.5
    with pytest.raises(InvalidCommercialMetricsError):
        CommercialImpact.model_validate(data)


# ---------------------------------------------------------------------------
# D. SessionBundle & Finding Tests
# ---------------------------------------------------------------------------
def test_session_bundle_schema_version(valid_session_bundle_dict, dummy_png_hash):
    data = copy.deepcopy(valid_session_bundle_dict)
    data["checksum"] = "a" * 64
    bundle = SessionBundle.model_validate(data)
    assert bundle.schema_version == "2.0.0"


def test_session_bundle_invalid_schema_version(valid_session_bundle_dict):
    data = copy.deepcopy(valid_session_bundle_dict)
    data["schema_version"] = "1.0.0"
    data["checksum"] = "a" * 64
    with pytest.raises(RevenueLeakScannerError):
        SessionBundle.model_validate(data)


def test_session_bundle_immutability(valid_session_bundle_dict):
    data = copy.deepcopy(valid_session_bundle_dict)
    data["checksum"] = "a" * 64
    bundle = SessionBundle.model_validate(data)
    with pytest.raises(ValidationError):
        bundle.domain = "hacked.com"


# ---------------------------------------------------------------------------
# E. Canonical JSON Determinism Tests
# ---------------------------------------------------------------------------
def test_canonical_json_determinism():
    dict_a = {"z": 1, "a": 2, "m": {"b": 3.1415926, "a": 1}}
    dict_b = {"a": 2, "m": {"a": 1, "b": 3.1415926}, "z": 1}

    bytes_a = encode_canonical_utf8(dict_a)
    bytes_b = encode_canonical_utf8(dict_b)

    assert bytes_a == bytes_b
    assert b'"a":2' in bytes_a
    assert b'"b":3.1416' in bytes_a  # Float rounding to 4 decimals


# ---------------------------------------------------------------------------
# F. SHA-256 Checksum Sealing Tests
# ---------------------------------------------------------------------------
def test_checksum_sealing_determinism(dummy_png_bytes, valid_session_bundle_dict):
    cs1 = calculate_sealed_checksum(dummy_png_bytes, valid_session_bundle_dict)
    cs2 = calculate_sealed_checksum(dummy_png_bytes, valid_session_bundle_dict)
    assert cs1 == cs2
    assert len(cs1) == 64


def test_checksum_changes_on_png_mutation(dummy_png_bytes, valid_session_bundle_dict):
    cs1 = calculate_sealed_checksum(dummy_png_bytes, valid_session_bundle_dict)
    mutated_png = dummy_png_bytes + b"EXTRA_BYTES"
    cs2 = calculate_sealed_checksum(mutated_png, valid_session_bundle_dict)
    assert cs1 != cs2


def test_checksum_changes_on_json_mutation(dummy_png_bytes, valid_session_bundle_dict):
    cs1 = calculate_sealed_checksum(dummy_png_bytes, valid_session_bundle_dict)
    mutated_dict = copy.deepcopy(valid_session_bundle_dict)
    mutated_dict["domain"] = "mutated.com"
    cs2 = calculate_sealed_checksum(dummy_png_bytes, mutated_dict)
    assert cs1 != cs2


# ---------------------------------------------------------------------------
# G. Write-Once Session Storage & Duplicate Protection Tests
# ---------------------------------------------------------------------------
def test_session_storage_save_and_get(tmp_path, dummy_png_bytes, valid_session_bundle_dict):
    storage = SessionStorage(base_storage_dir=tmp_path)
    domain = valid_session_bundle_dict["domain"]
    session_id = valid_session_bundle_dict["session_id"]

    # 1. Save new bundle
    bundle = storage.save_new_bundle(domain, session_id, dummy_png_bytes, valid_session_bundle_dict)
    assert bundle.domain == domain
    assert len(bundle.checksum) == 64

    # 2. Get and verify bundle
    loaded = storage.get_bundle(domain, session_id)
    assert loaded.session_id == bundle.session_id
    assert loaded.checksum == bundle.checksum


def test_session_storage_duplicate_protection(tmp_path, dummy_png_bytes, valid_session_bundle_dict):
    storage = SessionStorage(base_storage_dir=tmp_path)
    domain = valid_session_bundle_dict["domain"]
    session_id = valid_session_bundle_dict["session_id"]

    storage.save_new_bundle(domain, session_id, dummy_png_bytes, valid_session_bundle_dict)

    # Duplicate save must fail
    with pytest.raises(SessionExistsException):
        storage.save_new_bundle(domain, session_id, dummy_png_bytes, valid_session_bundle_dict)


def test_session_storage_no_update_api():
    storage = SessionStorage()
    assert not hasattr(storage, "update_bundle")
    assert not hasattr(storage, "overwrite_bundle")
    assert not hasattr(storage, "upsert_bundle")


# ---------------------------------------------------------------------------
# H. Tamper Detection Tests
# ---------------------------------------------------------------------------
def test_tamper_detection_modified_png(tmp_path, dummy_png_bytes, valid_session_bundle_dict):
    storage = SessionStorage(base_storage_dir=tmp_path)
    domain = valid_session_bundle_dict["domain"]
    session_id = valid_session_bundle_dict["session_id"]

    storage.save_new_bundle(domain, session_id, dummy_png_bytes, valid_session_bundle_dict)

    # Tamper with PNG file on disk
    png_path = storage.get_session_dir(domain, session_id) / f"session_{session_id}.png"
    
    # Temporarily allow write to modify file for tamper test
    import os, stat
    os.chmod(png_path, stat.S_IWRITE)
    with open(png_path, "wb") as f:
        f.write(b"TAMPERED_PNG_BYTES")

    with pytest.raises(ChecksumMismatchException):
        storage.get_bundle(domain, session_id)


def test_tamper_detection_modified_json(tmp_path, dummy_png_bytes, valid_session_bundle_dict):
    storage = SessionStorage(base_storage_dir=tmp_path)
    domain = valid_session_bundle_dict["domain"]
    session_id = valid_session_bundle_dict["session_id"]

    storage.save_new_bundle(domain, session_id, dummy_png_bytes, valid_session_bundle_dict)

    # Tamper with JSON sidecar on disk
    json_path = storage.get_session_dir(domain, session_id) / f"session_{session_id}.json"
    
    import os, stat
    os.chmod(json_path, stat.S_IWRITE)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    data["findings"][0]["product_name"] = "Hacked Product Name"
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(ChecksumMismatchException):
        storage.get_bundle(domain, session_id)


def test_tamper_detection_modified_checksum_file(tmp_path, dummy_png_bytes, valid_session_bundle_dict):
    storage = SessionStorage(base_storage_dir=tmp_path)
    domain = valid_session_bundle_dict["domain"]
    session_id = valid_session_bundle_dict["session_id"]

    storage.save_new_bundle(domain, session_id, dummy_png_bytes, valid_session_bundle_dict)

    # Tamper with .checksum file on disk
    checksum_path = storage.get_session_dir(domain, session_id) / f"session_{session_id}.checksum"
    
    import os, stat
    os.chmod(checksum_path, stat.S_IWRITE)
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write("f" * 64)

    with pytest.raises(ChecksumMismatchException):
        storage.get_bundle(domain, session_id)
