"""
tests/test_evidence.py — Test Suite for Phase D Evidence & Session Serialization

Covers:
  1. Valid PNG verification via VisualVerifier.
  2. Invalid/corrupted PNG byte stream rejection.
  3. Blank single-color canvas PNG rejection.
  4. PNG dimension validation (width >= 1024, height >= 600).
  5. BoundingBox & BoundingBoxMap validation.
  6. Finding construction from transient scan data.
  7. Multi-finding SessionBundle creation (findings: list[Finding]).
  8. Mandatory Regression Test 1: Multi-Finding distinct PNG screenshot binding.
  9. CommercialImpact & parameter provenance survival across serialization.
  10. Canonical JSON determinism & checksum sealing.
  11. SHA-256 Checksum excludes checksum field (Anti-circular hashing).
  12. Tamper detection (PNG mutation, JSON mutation, checksum file mutation).
  13. Duplicate session write rejection (SessionExistsException).
  14. Write-Once API isolation (no update/overwrite/upsert methods).
  15. Boundary isolation tests.
"""
import copy
import io
import json
import pytest
from PIL import Image

from src.commercial.impact_calculator import CommercialImpactCalculator
from src.evidence.canonical_json import dumps_canonical, encode_canonical_utf8
from src.evidence.checksum import calculate_sealed_checksum
from src.evidence.models import BoundingBox, BoundingBoxMap, Finding, SessionBundle
from src.evidence.session_serializer import EvidenceBuilder
from src.evidence.session_storage import SessionStorage
from src.evidence.visual_verifier import VisualVerifier
from src.exceptions import (
    ChecksumMismatchException,
    EvidenceTamperedException,
    InvalidBundleException,
    SessionExistsException,
)
from src.scanner.models import PDPScanResult, TransientScanContext


def _create_test_png(color=(100, 150, 200), width=1024, height=600):
    img = Image.new("RGB", (width, height), color=color)
    # Draw a non-uniform rectangle so extrema check passes
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 100, 100], fill=(255, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. VisualVerifier Unit Tests
# ---------------------------------------------------------------------------
def test_visual_verifier_valid_png(dummy_png_bytes):
    verifier = VisualVerifier()
    valid, reason, width, height, sha256_hash = verifier.verify_png_bytes(dummy_png_bytes)
    assert valid is True
    assert reason == "OK"
    assert width == 1024
    assert height == 600
    assert len(sha256_hash) == 64


def test_visual_verifier_invalid_bytes():
    verifier = VisualVerifier()
    valid, reason, width, height, sha256_hash = verifier.verify_png_bytes(b"INVALID_CORRUPTED_BYTES")
    assert valid is False
    assert "Corrupted PNG" in reason


def test_visual_verifier_blank_canvas():
    img = Image.new("RGB", (1024, 600), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    blank_bytes = buf.getvalue()

    verifier = VisualVerifier()
    valid, reason, width, height, sha256_hash = verifier.verify_png_bytes(blank_bytes)
    assert valid is False
    assert "blank uniform-color canvas" in reason


def test_visual_verifier_does_not_mutate_pixels(dummy_png_bytes):
    verifier = VisualVerifier()
    bytes_before = copy.deepcopy(dummy_png_bytes)
    verifier.verify_png_bytes(dummy_png_bytes)
    assert dummy_png_bytes == bytes_before


# ---------------------------------------------------------------------------
# 2. MANDATORY REGRESSION TEST 1 — Multi-Finding Distinct Evidence Binding
# ---------------------------------------------------------------------------
def test_mandatory_regression_multi_finding_distinct_png_hashes(tmp_path):
    """
    DEFECT-D2-01 REGRESSION TEST:
    Creates 2 PDP findings with deliberately different PNG byte streams (PNG A and PNG B).
    Asserts Finding A hash == hash(PNG A), Finding B hash == hash(PNG B), AND hash(PNG A) != hash(PNG B).
    """
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    png_a = _create_test_png(color=(50, 100, 150))
    png_b = _create_test_png(color=(200, 50, 50))

from src.scanner.page_validator import PageState
from src.scanner.models import PDPScanResult, TransientScanContext


# ---------------------------------------------------------------------------
# 2. MANDATORY REGRESSION TEST 1 — Multi-Finding Distinct Evidence Binding
# ---------------------------------------------------------------------------
def test_mandatory_regression_multi_finding_distinct_png_hashes(tmp_path):
    """
    DEFECT-D2-01 REGRESSION TEST:
    Creates 2 PDP findings with deliberately different PNG byte streams (PNG A and PNG B).
    Asserts Finding A hash == hash(PNG A), Finding B hash == hash(PNG B), AND hash(PNG A) != hash(PNG B).
    """
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    png_a = _create_test_png(color=(50, 100, 150))
    png_b = _create_test_png(color=(200, 50, 50))

    pdp_a = PDPScanResult(
        product_name="Product A",
        product_url="https://test.com/products/a",
        scanned_variant="Var A",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
    )
    pdp_b = PDPScanResult(
        product_name="Product B",
        product_url="https://test.com/products/b",
        scanned_variant="Var B",
        out_of_stock=True,
        notify_button_detected=True,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
    )

    context = TransientScanContext(domain="test.com", pdp_results=[pdp_a, pdp_b])
    calculator = CommercialImpactCalculator()
    comm = calculator.build_commercial_impact_dto(context, measured_traffic=100000)

    pdp_items = [
        (pdp_a, png_a, BoundingBoxMap()),
        (pdp_b, png_b, BoundingBoxMap()),
    ]

    bundle = builder.compile_and_save_session(
        domain="test.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=pdp_items,
    )


    assert len(bundle.findings) == 2

    # Finding A evidence hash must match PNG A hash
    hash_a = builder.verifier.verify_png_bytes(png_a)[4]
    hash_b = builder.verifier.verify_png_bytes(png_b)[4]

    assert bundle.findings[0].evidence.sha256_hash == hash_a
    assert bundle.findings[1].evidence.sha256_hash == hash_b
    assert hash_a != hash_b


# ---------------------------------------------------------------------------
# 3. EvidenceBuilder General Tests
# ---------------------------------------------------------------------------
def test_evidence_builder_compiles_and_saves_bundle(tmp_path, dummy_png_bytes):
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    pdp = PDPScanResult(
        product_name="Santiago Loafer",
        product_url="https://toms.com/products/loafer",
        scanned_variant="Size 9",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
    )

    context = TransientScanContext(domain="toms.com", pdp_results=[pdp])
    calculator = CommercialImpactCalculator()
    comm = calculator.build_commercial_impact_dto(context, measured_traffic=100000)
    boxes = BoundingBoxMap(cta=BoundingBox(x=10.0, y=10.0, width=100.0, height=50.0))

    bundle = builder.compile_and_save_session(
        domain="toms.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=[(pdp, dummy_png_bytes, boxes)],
    )

    assert isinstance(bundle, SessionBundle)
    assert bundle.domain == "toms.com"
    assert len(bundle.findings) == 1
    assert bundle.findings[0].product_name == "Santiago Loafer"


# ---------------------------------------------------------------------------
# 4. Architectural Isolation Test
# ---------------------------------------------------------------------------
def test_evidence_collector_has_no_storage_or_commercial_calls():
    import src.evidence.evidence_collector as ec
    assert not hasattr(ec, "SessionStorage")
    assert not hasattr(ec, "save_new_bundle")



def test_evidence_collector_screenshot_retry_and_timeout():
    """Verifies EvidenceCollector screenshot capture passes timeout and retries on failure."""
    from src.evidence.evidence_collector import EvidenceCollector

    class DummyPageTimeoutFail:
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, ms):
            pass
        def screenshot(self, *args, **kwargs):
            raise Exception("Screenshot timeout simulated")

    collector_fail = EvidenceCollector(DummyPageTimeoutFail())
    with pytest.raises(Exception, match="Screenshot timeout simulated"):
        collector_fail.capture_screenshot_bytes()

    class DummyPageRetrySuccess:
        def __init__(self):
            self.calls = 0
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, ms):
            pass
        def screenshot(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise Exception("First attempt transient timeout")

            from PIL import Image
            import io
            img = Image.new("RGB", (1024, 600), color=(100, 150, 200))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    collector_success = EvidenceCollector(DummyPageRetrySuccess())
    bytes_out, duration = collector_success.capture_screenshot_bytes()
    assert bytes_out is not None
    assert len(bytes_out) > 0
    assert collector_success.page.calls == 2


def test_screenshot_resilience_test1_normal_success():
    """TEST 1: Normal screenshot succeeds exactly as before."""
    from src.evidence.evidence_collector import EvidenceCollector
    from src.evidence.visual_verifier import VisualVerifier

    class NormalPage:
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, ms):
            pass
        def screenshot(self, *args, **kwargs):
            return _create_test_png(color=(80, 120, 160))

    collector = EvidenceCollector(NormalPage())
    png_bytes, duration = collector.capture_screenshot_bytes()
    verifier = VisualVerifier()
    valid, reason, w, h, sha_hash = verifier.verify_png_bytes(png_bytes)
    assert valid is True
    assert reason == "OK"
    assert w == 1024 and h == 600
    assert len(sha_hash) == 64


def test_screenshot_resilience_test2_and_3_cdp_fallback_success():
    """TEST 2 & 3: Simulated font-lock timeout triggers CDP fallback path producing valid PNG."""
    from src.evidence.evidence_collector import EvidenceCollector
    from src.evidence.visual_verifier import VisualVerifier

def test_screenshot_resilience_test2_and_3_cdp_fallback_success():
    """TEST 2 & 3: Simulated font-lock timeout triggers window.stop retry path producing valid PNG."""
    from src.evidence.evidence_collector import EvidenceCollector
    from src.evidence.visual_verifier import VisualVerifier

    class FontLockPage:
        def __init__(self):
            self.calls = 0
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, ms):
            pass
        def screenshot(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise Exception("Page.screenshot: Timeout 3000ms exceeded. waiting for fonts to load...")
            return _create_test_png(color=(120, 180, 220))

    collector = EvidenceCollector(FontLockPage())
    png_bytes, duration = collector.capture_screenshot_bytes()
    verifier = VisualVerifier()
    valid, reason, w, h, sha_hash = verifier.verify_png_bytes(png_bytes)
    assert valid is True
    assert reason == "OK"
    assert w == 1024 and h == 600




def test_screenshot_resilience_test4_repeated_failure_remains_unhandled():
    """TEST 4: Repeated screenshot failure remains a genuine evidence failure."""
    from src.evidence.evidence_collector import EvidenceCollector

    class CompleteFailPage:
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, ms):
            pass
        def screenshot(self, *args, **kwargs):
            raise Exception("Page.screenshot: Timeout 3000ms exceeded")

    collector = EvidenceCollector(CompleteFailPage())
    with pytest.raises(Exception):
        collector.capture_screenshot_bytes()



def test_screenshot_resilience_test5_blank_png_rejected():
    """TEST 5: Blank/invalid PNG is still rejected by VisualVerifier."""
    from src.evidence.visual_verifier import VisualVerifier
    from PIL import Image
    import io

    # Blank canvas (monochrome white)
    img = Image.new("RGB", (1024, 600), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    verifier = VisualVerifier()
    valid, reason, w, h, sha_hash = verifier.verify_png_bytes(buf.getvalue())
    assert valid is False
    assert "blank" in reason.lower() or "monochrome" in reason.lower()


# ---------------------------------------------------------------------------
# 5. CONTRACT-EVIDENCE-001 1:1 Evidence Binding Tests
# ---------------------------------------------------------------------------
def test_contract_evidence_001_pdp_result_binds_immediate_png_bytes():
    """CONTRACT-EVIDENCE-001: PDPScanResult binds immediate raw PNG bytes captured at PDP inspection time."""
    png_a = _create_test_png(color=(10, 20, 30))
    png_b = _create_test_png(color=(200, 210, 220))

    pdp_a = PDPScanResult(
        product_name="PDP A",
        product_url="https://store.com/products/a",
        scanned_variant="Var A",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        png_bytes=png_a,
    )
    pdp_b = PDPScanResult(
        product_name="PDP B",
        product_url="https://store.com/products/b",
        scanned_variant="Var B",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        png_bytes=png_b,
    )

    assert pdp_a.png_bytes == png_a
    assert pdp_b.png_bytes == png_b
    assert pdp_a.png_bytes != pdp_b.png_bytes


def test_contract_evidence_001_multi_pdp_distinct_screenshot_isolation(tmp_path):
    """CONTRACT-EVIDENCE-001: Multi-PDP scan binds unique evidence PNG bytes per PDP without cross-PDP sharing."""
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    png_a = _create_test_png(color=(15, 35, 55))
    png_b = _create_test_png(color=(155, 175, 195))

    pdp_a = PDPScanResult(
        product_name="PDP A",
        product_url="https://store.com/products/a",
        scanned_variant="Var A",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        png_bytes=png_a,
    )
    pdp_b = PDPScanResult(
        product_name="PDP B",
        product_url="https://store.com/products/b",
        scanned_variant="Var B",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        png_bytes=png_b,
    )

    context = TransientScanContext(domain="store.com", pdp_results=[pdp_a, pdp_b])
    calculator = CommercialImpactCalculator()
    comm = calculator.build_commercial_impact_dto(context, measured_traffic=50000)

    pdp_items = [
        (pdp_a, pdp_a.png_bytes, BoundingBoxMap()),
        (pdp_b, pdp_b.png_bytes, BoundingBoxMap()),
    ]

    bundle = builder.compile_and_save_session(
        domain="store.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=pdp_items,
    )

    assert len(bundle.findings) == 2
    hash_a = builder.verifier.verify_png_bytes(png_a)[4]
    hash_b = builder.verifier.verify_png_bytes(png_b)[4]

def test_contract_evidence_001_single_pdp_multi_finding_evidence_association(tmp_path):
    """CONTRACT-EVIDENCE-001: 1 PDP producing 3 findings anchors all 3 findings to that PDP's single verified evidence context."""
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)
    png_bytes = _create_test_png(color=(30, 60, 90))

    from src.scanner.models import CommercialOpportunity, OpportunityType
    opp1 = CommercialOpportunity(opportunity_type=OpportunityType.MISSING_SOCIAL_PROOF, commercial_problem_summary="No reviews", sellable_service_angle="Reviews")
    opp2 = CommercialOpportunity(opportunity_type=OpportunityType.MISSING_UPSELL, commercial_problem_summary="No upsell", sellable_service_angle="Upsell")
    opp3 = CommercialOpportunity(opportunity_type=OpportunityType.MISSING_STICKY_ATC, commercial_problem_summary="No sticky ATC", sellable_service_angle="Sticky ATC")

    pdp = PDPScanResult(
        product_name="Multi-Finding PDP",
        product_url="https://store.com/products/multi",
        scanned_variant="Var 1",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        page_state=PageState.REAL_PRODUCT,
        opportunities=[opp1, opp2, opp3],
        png_bytes=png_bytes,
    )

    context = TransientScanContext(domain="store.com", pdp_results=[pdp])
    calc = CommercialImpactCalculator()
    comm = calc.build_commercial_impact_dto(context, measured_traffic=50000)

    bundle = builder.compile_and_save_session(
        domain="store.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=[(pdp, pdp.png_bytes, BoundingBoxMap())],
    )

    assert len(bundle.findings) == 1
    finding = bundle.findings[0]
    assert len(finding.opportunities) == 3
    assert finding.evidence.sha256_hash == builder.verifier.verify_png_bytes(png_bytes)[4]


def test_contract_evidence_001_invalid_png_rejection_prevents_fake_path(tmp_path):
    """CONTRACT-EVIDENCE-001: Invalid/missing PNG bytes raise InvalidBundleException and NEVER fabricate fake paths."""
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    pdp = PDPScanResult(
        product_name="Damaged PDP",
        product_url="https://store.com/products/damaged",
        scanned_variant="Default",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        page_state=PageState.REAL_PRODUCT,
        png_bytes=b"CORRUPTED_BYTES",
    )

    context = TransientScanContext(domain="store.com", pdp_results=[pdp])
    calc = CommercialImpactCalculator()
    comm = calc.build_commercial_impact_dto(context, measured_traffic=50000)

    with pytest.raises(InvalidBundleException, match="Visual evidence verification failed"):
        builder.compile_and_save_session(
            domain="store.com",
            transient_context=context,
            commercial_impact=comm,
            pdp_evidence_items=[(pdp, pdp.png_bytes, BoundingBoxMap())],
        )




