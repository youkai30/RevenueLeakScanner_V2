"""
tests/test_remediation_phase5.py — Verification tests for Phase 5 remediation.

Covers:
- DEF-BB-01: Multi-PDP screenshot unique saving & bindings.
- DEF-BB-02: Review platform selectors syntax safety & text fallback rejection.
- DEF-BB-03: Measured traffic fallback financial status mapping.
- DEF-BB-04: Default variant DOM picker check for uncertainty.
- DEF-BB-05 & Path Integrity: Vacuous evidence logic, physical file existence checks.
- URL Heuristics: Collections products URLs allowance.
- Production Integration: Flow verification of multi-findings, screenshot matching, and status assertions.
"""
import os
import shutil
import pytest
import uuid
from pathlib import Path
from src.commercial.lead_exporter import CommercialLeadExporter
from src.commercial.impact_calculator import CommercialImpactCalculator
from src.evidence.session_serializer import EvidenceBuilder
from src.evidence.session_storage import SessionStorage
from src.evidence.models import SessionBundle, CommercialImpact, Finding, VisualEvidence, BoundingBoxMap
from src.scanner.models import PDPScanResult, CommercialOpportunity, OpportunityType, EvidenceStatus, PageState, TransientScanContext
from src.scanner.cro_stack_detector import CROStackDetector
from src.scanner.detection_state import DetectionState
from src.scanner.variant_matrix import VariantMatrixScanner, VariantInfo
from src.scanner.product_discovery import ProductDiscoveryEngine
from src.config import SESSIONS_DIR

class DummyElement:
    def __init__(self, text="", val="", aria="", disabled=False, visible=True):
        self._text = text
        self._val = val
        self._aria = aria
        self._disabled = disabled
        self._visible = visible

    def text_content(self):
        return self._text

    def get_attribute(self, attr):
        if attr == "value":
            return self._val
        if attr == "aria-label":
            return self._aria
        if attr == "disabled":
            return "true" if self._disabled else None
        if attr == "class":
            return "variant-selector"
        return None

    def is_disabled(self):
        return self._disabled

    def is_visible(self):
        return self._visible

    def evaluate(self, script):
        if "position" in script:
            return "fixed"
        if "closest" in script:
            return False
        return "fixed"

class DummyPage:
    def __init__(self, content_dict=None, elements_dict=None):
        self.content_dict = content_dict or {}
        self.elements_dict = elements_dict or {}

    def evaluate(self, script, *args):
        if "mapVariants" in script or "ShopifyAnalytics" in script or "Shopify.product" in script:
            return self.content_dict.get("js_variants")
        if "position" in script:
            return "fixed"
        if "scrollHeight" in script:
            return 1500
        if "els.some" in script:
            return False
        return None

    def query_selector(self, selector):
        return self.elements_dict.get(selector)

    def query_selector_all(self, selector):
        return self.elements_dict.get(selector, [])

    def inner_text(self, selector):
        return self.content_dict.get("inner_text", "")


# ===========================================================================
# DEF-BB-01: Multi-PDP Screenshot Evidence Loss
# ===========================================================================

def test_def_bb_01_multi_pdp_screenshot_evidence(tmp_path):
    """Verify each Finding saves its own distinct screenshot with unique binding."""
    from io import BytesIO
    from PIL import Image

    def gen_png(color):
        img = Image.new("RGBA", (1024, 600), color=color)
        img.putpixel((0, 0), (255, 255, 255, 255) if color != "white" else (0, 0, 0, 255))
        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)
    
    session_id = uuid.uuid4()
    build_id = uuid.uuid4()
    
    # 3 distinct findings and 3 different PNG payloads
    png1 = gen_png("red")
    png2 = gen_png("green")
    png3 = gen_png("blue")
    
    pdp1 = PDPScanResult(
        product_name="P1", product_url="https://teststore.com/products/p1",
        scanned_variant="S1", out_of_stock=True, page_state=PageState.REAL_PRODUCT,
        variants_inspected=1, variants_oos=1,
        notify_button_detected=False, sold_out_detected=False
    )
    pdp2 = PDPScanResult(
        product_name="P2", product_url="https://teststore.com/products/p2",
        scanned_variant="S2", out_of_stock=True, page_state=PageState.REAL_PRODUCT,
        variants_inspected=1, variants_oos=1,
        notify_button_detected=False, sold_out_detected=False
    )
    pdp3 = PDPScanResult(
        product_name="P3", product_url="https://teststore.com/products/p3",
        scanned_variant="S3", out_of_stock=True, page_state=PageState.REAL_PRODUCT,
        variants_inspected=1, variants_oos=1,
        notify_button_detected=False, sold_out_detected=False
    )
    
    context = TransientScanContext(domain="teststore.com", pdp_results=[pdp1, pdp2, pdp3])
    commercial = CommercialImpact(
        est_monthly_loss_usd=500.0, est_monthly_traffic=10000,
        lead_priority="MEDIUM", confidence_score=0.75,
        variants_inspected=3, variants_oos=3, financial_loss_status="ESTIMATED",
        oos_frequency_pct=100.0
    )
    
    evidence_items = [
        (pdp1, png1, BoundingBoxMap()),
        (pdp2, png2, BoundingBoxMap()),
        (pdp3, png3, BoundingBoxMap()),
    ]
    
    bundle = builder.compile_and_save_session(
        domain="teststore.com",
        transient_context=context,
        commercial_impact=commercial,
        pdp_evidence_items=evidence_items,
        session_id=session_id,
        build_id=build_id
    )
    
    # Assert 3 files exist and filenames are unique
    session_dir = storage.get_session_dir("teststore.com", session_id)
    assert len(bundle.findings) == 3
    
    # Backward compatibility file session_<session_id>.png must exist
    assert (session_dir / f"session_{session_id}.png").exists()
    
    for f in bundle.findings:
        assert f.evidence.image_file.startswith(f"session_{session_id}_")
        assert f.evidence.image_file.endswith(".png")
        
        # Verify physical screenshot path
        physical_path = session_dir / f.evidence.image_file
        assert physical_path.exists()
        
        # Verify content bytes matches
        with open(physical_path, "rb") as fp:
            file_bytes = fp.read()
        if f.product_name == "P1":
            assert file_bytes == png1
        elif f.product_name == "P2":
            assert file_bytes == png2
        elif f.product_name == "P3":
            assert file_bytes == png3


# ===========================================================================
# DEF-BB-02: Invalid Review Platform Selectors
# ===========================================================================

def test_def_bb_02_selector_safety():
    """Verify domain strings are not passed directly to query_selector and script triggers TRUE."""
    el = DummyElement()
    
    # Yotpo script tag selector -> matches script elements, not plain domain
    page_yotpo = DummyPage(elements_dict={"script[src*='yotpo.com']": el})
    detector_yotpo = CROStackDetector(page_yotpo)
    res_yotpo = detector_yotpo.detect_review_state()
    assert res_yotpo.state == DetectionState.TRUE
    assert res_yotpo.details == "Yotpo"

    # Okendo script tag selector
    page_okendo = DummyPage(elements_dict={"script[src*='okendo.io']": el})
    detector_okendo = CROStackDetector(page_okendo)
    res_okendo = detector_okendo.detect_review_state()
    assert res_okendo.state == DetectionState.TRUE
    assert res_okendo.details == "Okendo"

    # Loox iframe selector
    page_loox = DummyPage(elements_dict={"iframe[src*='loox']": el})
    detector_loox = CROStackDetector(page_loox)
    res_loox = detector_loox.detect_review_state()
    assert res_loox.state == DetectionState.TRUE
    assert res_loox.details == "Loox"

    # Bazaarvoice script selector
    page_bv = DummyPage(elements_dict={"script[src*='bazaarvoice.com']": el})
    detector_bv = CROStackDetector(page_bv)
    res_bv = detector_bv.detect_review_state()
    assert res_bv.state == DetectionState.TRUE
    assert res_bv.details == "Bazaarvoice"

    # Plain text "yotpo.com" in inner_text MUST NOT return TRUE
    page_text = DummyPage(content_dict={"inner_text": "Buy from us, read about yotpo.com"})
    detector_text = CROStackDetector(page_text)
    res_text = detector_text.detect_review_state()
    # It shouldn't match plain text as review platform verified presence
    assert res_text.state != DetectionState.TRUE


# ===========================================================================
# DEF-BB-03: Incorrect VERIFIED Financial Status
# ===========================================================================

def test_def_bb_03_financial_status():
    """Verify measured traffic values map to correct loss status."""
    calculator = CommercialImpactCalculator()
    
    # Prices exist
    pdp = PDPScanResult(
        product_name="P", product_url="https://t.com/p", scanned_variant="V",
        out_of_stock=True, notify_button_detected=False, sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT, variants_inspected=1, variants_oos=1,
        inspected_prices=[25.0]
    )
    context = TransientScanContext(domain="t.com", pdp_results=[pdp])
    
    # None traffic -> ESTIMATED
    res_none = calculator.compute_impact(context, measured_traffic=None)
    assert res_none.financial_loss_status == "ESTIMATED"
    
    # 0 traffic -> ESTIMATED
    res_zero = calculator.compute_impact(context, measured_traffic=0)
    assert res_zero.financial_loss_status == "ESTIMATED"
    
    # -1 traffic -> ESTIMATED
    res_neg = calculator.compute_impact(context, measured_traffic=-1)
    assert res_neg.financial_loss_status == "ESTIMATED"
    
    # 1000 traffic + prices -> VERIFIED
    res_pos = calculator.compute_impact(context, measured_traffic=1000)
    assert res_pos.financial_loss_status == "VERIFIED"


# ===========================================================================
# DEF-BB-04: Default Variant Extraction Uncertainty
# ===========================================================================

def test_def_bb_04_default_variant_uncertainty():
    """Verify Default Title with visible variant picker returns True (uncertain)."""
    el = DummyElement()
    
    # Default Title + visible swatch variant picker element
    page = DummyPage(elements_dict={".swatch": [el]})
    scanner = VariantMatrixScanner(page)
    
    inspected = [VariantInfo(sku_name="Default Title", option_type="Variant", is_available=True)]
    assert scanner.is_extraction_uncertain(inspected) is True
    
    # Default Title + no selectors in DOM -> False (certain)
    page_empty = DummyPage()
    scanner_empty = VariantMatrixScanner(page_empty)
    assert scanner_empty.is_extraction_uncertain(inspected) is False
    
    # Multiple real extracted variants -> False (certain)
    inspected_multi = [
        VariantInfo(sku_name="Red", option_type="Variant", is_available=True),
        VariantInfo(sku_name="Blue", option_type="Variant", is_available=True)
    ]
    assert scanner_empty.is_extraction_uncertain(inspected_multi) is False


# ===========================================================================
# DEF-BB-05 & Path Integrity: Vacuous Evidence
# ===========================================================================

def test_def_bb_05_evidence_validity_gates(tmp_path):
    """Verify evidence_validity states and physical file checks."""
    # Ensure SESSIONS_DIR patch/override matches our tmp_path directory in exporter
    shutil.rmtree(SESSIONS_DIR / "tomstests.com", ignore_errors=True)
    
    exporter = CommercialLeadExporter()
    
    # Case 1: Zero findings -> NONE_DETECTED
    bundle_empty = SessionBundle.model_construct(
        domain="tomstests.com", session_id=uuid.uuid4(), build_id=uuid.uuid4(),
        scanner_version="2.3.1", checksum="1"*64, timestamp="2026-08-10T12:00:00Z",
        findings=[],
        commercial=CommercialImpact(
            est_monthly_loss_usd=0.0, est_monthly_traffic=10000,
            lead_priority="LOW", confidence_score=0.5,
            variants_inspected=0, variants_oos=0, financial_loss_status="UNKNOWN",
            oos_frequency_pct=0.0
        )
    )
    lead_empty = exporter.assemble_lead(bundle_empty)
    assert lead_empty.evidence_validity == "NONE_DETECTED"
    
    # Case 2: Findings with physical file existing -> VERIFIED
    session_id = uuid.uuid4()
    pdp_url = "https://tomstests.com/products/p"
    evidence_id = uuid.uuid4()
    finding_id = uuid.uuid4()
    img_file = f"session_{session_id}_{evidence_id}.png"
    
    # Write the physical file to where the exporter checks
    dest_dir = SESSIONS_DIR / "tomstests.com" / str(session_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(dest_dir / img_file, "wb") as fp:
        fp.write(b"MOCK_PNG_DATA")
        
    findings = [
        Finding(
            finding_id=finding_id, product_name="P", product_url=pdp_url,
            scanned_variant="V", out_of_stock=True, notify_button_detected=False,
            sold_out_detected=True, review_widget_detected=False, review_platform="",
            review_count=0, upsell_detected=False, sticky_atc_detected=False,
            page_state="REAL_PRODUCT", bis_detection_state="FALSE",
            review_detection_state="FALSE", upsell_detection_state="FALSE",
            sticky_atc_detection_state="FALSE",
            evidence=VisualEvidence(
                image_file=img_file, relative_path=f"tomstests.com/{session_id}/{img_file}",
                width=1024, height=600, sha256_hash="f"*64, capture_duration_ms=200,
                browser_version="Chrome", viewport="1024x600", valid=True,
                finding_id=str(finding_id), pdp_url=pdp_url, store_domain="tomstests.com",
                evidence_id=str(evidence_id)
            ),
            opportunities=[
                CommercialOpportunity(
                    opportunity_type=OpportunityType.REVENUE_LEAK,
                    commercial_problem_summary="Out-of-Stock variant has no Back-in-Stock capture modal",
                    sellable_service_angle="Back-In-Stock Restock Capture Flow",
                    is_valid_opportunity=True,
                    evidence_status=EvidenceStatus.VERIFIED,
                ).model_dump(mode="json")
            ]
        )
    ]
    
    bundle_valid = SessionBundle(
        domain="tomstests.com", session_id=session_id, build_id=uuid.uuid4(),
        scanner_version="2.3.1", checksum="1"*64, timestamp="2026-08-10T12:00:00Z",
        findings=findings,
        commercial=CommercialImpact(
            est_monthly_loss_usd=100.0, est_monthly_traffic=10000,
            lead_priority="LOW", confidence_score=0.7,
            variants_inspected=1, variants_oos=1, financial_loss_status="ESTIMATED",
            oos_frequency_pct=100.0
        ),
        contact_info={"instagram_url": "https://instagram.com/t"}
    )
    
    lead_valid = exporter.assemble_lead(bundle_valid)
    assert lead_valid.evidence_validity == "VERIFIED"
    assert lead_valid.lead_class == "A — SELLABLE"
    
    # Case 3: Physically delete file -> fails exists check -> not Class A
    os.remove(dest_dir / img_file)
    lead_deleted = exporter.assemble_lead(bundle_valid)
    assert lead_deleted.evidence_validity != "VERIFIED"
    assert lead_deleted.lead_class != "A — SELLABLE"
    
    # Clean up
    shutil.rmtree(SESSIONS_DIR / "tomstests.com", ignore_errors=True)


# ===========================================================================
# URL Heuristics Rejection Allowance
# ===========================================================================

def test_url_heuristics_candidate_rejections():
    """Verify PDP URL heuristics reordering logic allows collections products."""
    engine = ProductDiscoveryEngine()
    
    # /products/blue-shirt -> accepted
    valid1, _ = engine.is_valid_pdp_url("test.com", "https://test.com/products/blue-shirt")
    assert valid1 is True
    
    # /collections/all -> rejected
    valid2, _ = engine.is_valid_pdp_url("test.com", "https://test.com/collections/all")
    assert valid2 is False
    
    # /collections/all/products/blue-shirt -> accepted
    valid3, _ = engine.is_valid_pdp_url("test.com", "https://test.com/collections/all/products/blue-shirt")
    assert valid3 is True
    
    # /products/size-guide -> rejected
    valid4, _ = engine.is_valid_pdp_url("test.com", "https://test.com/products/size-guide")
    assert valid4 is False
