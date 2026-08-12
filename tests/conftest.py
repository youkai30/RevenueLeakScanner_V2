"""
tests/conftest.py — Pytest Fixtures for Phase A Foundation
"""
import io
import pytest
from PIL import Image

from src.evidence.checksum import calculate_png_hash_hex


@pytest.fixture
def dummy_png_bytes() -> bytes:
    """Generates a deterministic 1024x600 PNG image byte stream with non-uniform pattern for testing."""
    img = Image.new("RGB", (1024, 600), color=(73, 109, 137))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 400, 300], fill=(200, 100, 50))
    draw.text((100, 100), "TEST EVIDENCE CANVAS", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()



@pytest.fixture
def dummy_png_hash(dummy_png_bytes: bytes) -> str:
    """Returns SHA-256 hex string of dummy PNG fixture."""
    return calculate_png_hash_hex(dummy_png_bytes)


@pytest.fixture
def valid_finding_dict(dummy_png_hash: str) -> dict:
    """Returns a valid Finding dictionary representation."""
    return {
        "finding_id": "11111111-1111-4111-8111-111111111111",
        "product_name": "Santiago Loafer Navy Mesh",
        "product_url": "https://toms.com/products/mens-santiago-loafer-navy-mesh",
        "scanned_variant": "Size 8.5 / Navy Mesh",
        "out_of_stock": True,
        "notify_button_detected": False,
        "sold_out_detected": True,
        "review_widget_detected": True,
        "review_platform": "Customer Reviews",
        "review_count": 38,
        "upsell_detected": True,
        "sticky_atc_detected": True,
        "evidence": {
            "image_file": "session_22222222-2222-4222-8222-222222222222.png",
            "relative_path": "toms.com/22222222-2222-4222-8222-222222222222/session_22222222-2222-4222-8222-222222222222.png",
            "width": 1024,
            "height": 600,
            "sha256_hash": dummy_png_hash,
            "capture_duration_ms": 450,
            "browser_version": "Chromium 118.0",
            "viewport": "1365x900",
            "valid": True,
            "validation_reason": "OK",
        },
        "bounding_boxes": {
            "buy_box": {"x": 860.0, "y": 460.0, "width": 450.0, "height": 115.0},
            "cta": {"x": 860.0, "y": 617.0, "width": 450.0, "height": 47.0},
        },
    }


@pytest.fixture
def valid_commercial_dict() -> dict:
    """Returns a valid CommercialImpact dictionary representation."""
    return {
        "est_monthly_traffic": 120000,
        "oos_frequency_pct": 12.5,
        "variants_inspected": 40,
        "variants_oos": 5,
        "est_monthly_loss_usd": 24480.0,
        "lead_priority": "HIGH",
        "confidence_score": 0.95,
    }


@pytest.fixture
def valid_session_bundle_dict(valid_finding_dict: dict, valid_commercial_dict: dict) -> dict:
    """Returns a valid SessionBundle dictionary payload (without checksum)."""
    return {
        "schema_version": "2.0.0",
        "scanner_version": "2.3.1",
        "session_id": "22222222-2222-4222-8222-222222222222",
        "build_id": "33333333-3333-4333-8333-333333333333",
        "domain": "toms.com",
        "timestamp": "2026-08-07T12:00:00+00:00",
        "findings": [valid_finding_dict],
        "commercial": valid_commercial_dict,
    }
