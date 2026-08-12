"""
tests/test_remediation_phase3.py — Comprehensive validation tests for Phase 3.

Covers:
- DEF-05: Price extraction, conversion, inspected_prices, and financial status flags.
- DEF-06: Strict Class A safety gates (validating PDP, detector state, evidence, and financial bounds).
- DEF-07: Expanded CRO Review selectors and script source checks.
"""
import pytest
import uuid
from src.commercial.lead_exporter import CommercialLeadExporter
from src.commercial.lead_exporter import CommercialLeadRecord
from src.commercial.impact_calculator import CommercialImpactCalculator
from src.evidence.models import SessionBundle, CommercialImpact, Finding, VisualEvidence
from src.scanner.models import PDPScanResult, CommercialOpportunity, OpportunityType, EvidenceStatus, PageState
from src.scanner.detection_state import DetectionState, DetectionFailureReason, DetectionResult
from src.scanner.cro_stack_detector import CROStackDetector

class DummyElement:
    def __init__(self, text="", val="", aria="", disabled=False):
        self._text = text
        self._val = val
        self._aria = aria
        self._disabled = disabled

    def text_content(self):
        return self._text

    def get_attribute(self, attr):
        if attr == "value":
            return self._val
        if attr == "aria-label":
            return self._aria
        if attr == "disabled":
            return "true" if self._disabled else None
        return None

    def is_disabled(self):
        return self._disabled

    def is_visible(self):
        return True

    def evaluate(self, script):
        return "fixed"

class DummyPage:
    def __init__(self, content_dict=None, elements_dict=None):
        self.content_dict = content_dict or {}
        self.elements_dict = elements_dict or {}

    def evaluate(self, script, *args):
        # Mock evaluation for Shopify variants script
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
        return ""


# ===========================================================================
# DEF-05 — Financial Calculation Reliability
# ===========================================================================

def test_shopify_variant_price_conversion():
    """Verify JS mapVariants extracts price in cents and converts to float dollars."""
    from src.scanner.variant_matrix import VariantMatrixScanner, _JS_VARIANT_EXTRACTION_SCRIPT
    
    # Assert that the JS script contains the conversion logic
    assert "100.0" in _JS_VARIANT_EXTRACTION_SCRIPT or "100" in _JS_VARIANT_EXTRACTION_SCRIPT

    # Simulating returned mapped value from JS (which has divided cents to dollars)
    mock_js_data = {
        "source": "ShopifyAnalytics",
        "variants": [
            {
                "id": "111",
                "title": "Red / Small",
                "available": True,
                "price": 29.99,
                "option1": "Red",
                "option2": "Small",
                "option3": ""
            }
        ]
    }
    
    page = DummyPage(content_dict={"js_variants": mock_js_data})
    scanner = VariantMatrixScanner(page)
    variants = scanner.inspect_variants()
    
    assert len(variants) == 1
    assert variants[0].variant_id == "111"
    assert variants[0].price_usd == 29.99


def test_missing_price_handling():
    """Verify that missing price fields are safely ignored or parsed as 0.0, not causing crash."""
    from src.scanner.variant_matrix import VariantMatrixScanner
    
    mock_js_data = {
        "source": "Shopify.product",
        "variants": [
            {
                "id": "222",
                "title": "Default Title",
                "available": True,
                "option1": "",
                "option2": "",
                "option3": ""
                # no price field
            }
        ]
    }
    
    page = DummyPage(content_dict={"js_variants": mock_js_data})
    scanner = VariantMatrixScanner(page)
    variants = scanner.inspect_variants()
    
    assert len(variants) == 1
    assert variants[0].price_usd == 0.0


def test_financial_status_unknown_total_inspected_zero():
    """Verify financial_loss_status is UNKNOWN when variants_inspected is 0."""
    from src.scanner.models import TransientScanContext
    
    calculator = CommercialImpactCalculator()
    context = TransientScanContext(domain="test.com", pdp_results=[])
    
    res = calculator.compute_impact(context)
    assert res.financial_loss_status == "UNKNOWN"
    assert res.est_monthly_loss_usd == 0.0


def test_financial_status_verified():
    """Verify financial_loss_status is VERIFIED when traffic is measured and prices are present."""
    from src.scanner.models import TransientScanContext
    
    calculator = CommercialImpactCalculator()
    pdp = PDPScanResult(
        product_name="Product",
        product_url="https://test.com/p",
        scanned_variant="V",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        variants_inspected=1,
        variants_oos=1,
        inspected_prices=[49.99],
    )
    context = TransientScanContext(domain="test.com", pdp_results=[pdp])
    
    res = calculator.compute_impact(context, measured_traffic=10000)
    assert res.financial_loss_status == "VERIFIED"
    assert res.est_monthly_loss_usd > 0.0


def test_financial_status_estimated_traffic_fallback():
    """Verify financial_loss_status is ESTIMATED when traffic is fallback (measured_traffic is None)."""
    from src.scanner.models import TransientScanContext
    
    calculator = CommercialImpactCalculator()
    pdp = PDPScanResult(
        product_name="Product",
        product_url="https://test.com/p",
        scanned_variant="V",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        variants_inspected=1,
        variants_oos=1,
        inspected_prices=[49.99],
    )
    context = TransientScanContext(domain="test.com", pdp_results=[pdp])
    
    res = calculator.compute_impact(context, measured_traffic=None)
    assert res.financial_loss_status == "ESTIMATED"
    assert res.est_monthly_loss_usd > 0.0


# ===========================================================================
# DEF-06 — Class A Scoring Safety
# ===========================================================================

def _create_base_class_a_bundle(
    page_state=PageState.REAL_PRODUCT,
    bis_det="FALSE",
    review_det="FALSE",
    upsell_det="FALSE",
    sticky_det="FALSE",
    evidence_valid=True,
    binding_valid=True,
    financial_status="VERIFIED",
    est_loss=500.0,
    has_contact=True,
):
    finding_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    
    finding_finding_id = finding_id if binding_valid else uuid.uuid4()
    
    findings = [
        Finding(
            finding_id=finding_id,
            product_name="Product M",
            product_url="https://test.com/products/p1",
            scanned_variant="M",
            out_of_stock=True,
            notify_button_detected=False,
            sold_out_detected=True,
            review_widget_detected=False,
            review_platform="",
            review_count=0,
            upsell_detected=False,
            sticky_atc_detected=False,
            page_state=page_state.value if hasattr(page_state, "value") else str(page_state),
            bis_detection_state=bis_det,
            review_detection_state=review_det,
            upsell_detection_state=upsell_det,
            sticky_atc_detection_state=sticky_det,
            evidence=VisualEvidence(
                image_file="screenshot.png",
                relative_path="https://test.com/products/p1/screenshot.png",
                sha256_hash="1c9b1846131b4a7680e53763aeb6493e9031b7d1118813d7d930bb593a99e381",
                width=1024,
                height=600,
                viewport="1024x600",
                capture_duration_ms=450,
                browser_version="Chrome",
                valid=evidence_valid,
                finding_id=str(finding_finding_id),
                pdp_url="https://test.com/products/p1",
                store_domain="test.com",
                evidence_id=str(evidence_id),
            ),
            opportunities=[
                CommercialOpportunity(
                    opportunity_type=OpportunityType.REVENUE_LEAK,
                    commercial_problem_summary="Out-of-Stock variant 'M' has no Back-in-Stock capture modal",
                    sellable_service_angle="Back-In-Stock Restock Capture Flow",
                    is_valid_opportunity=True,
                    evidence_status=EvidenceStatus.VERIFIED,
                ).model_dump(mode="json")
            ]
        )
    ]
    
    # 3 PDPs required for FULL coverage Class A check in lead_exporter
    findings_3 = findings * 3
    
    session_id = uuid.uuid4()
    from src.config import SESSIONS_DIR
    for f in findings_3:
        if f.evidence and f.evidence.image_file:
            path = SESSIONS_DIR / "test.com" / str(session_id) / f.evidence.image_file
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as fp:
                fp.write(b"MOCK_PNG_DATA")

    contact_info = {}
    if has_contact:
        contact_info = {"instagram_url": "https://instagram.com/test"}
        
    return SessionBundle(
        domain="test.com",
        session_id=session_id,
        build_id=uuid.uuid4(),
        scanner_version="2.3.1",
        checksum="1111111111111111111111111111111111111111111111111111111111111111",
        schema_version="2.0.0",
        timestamp="2026-08-10T12:00:00Z",
        commercial=CommercialImpact(
            est_monthly_loss_usd=est_loss,
            est_monthly_traffic=10000,
            lead_priority="HIGH",
            confidence_score=0.85,
            oos_frequency_pct=10.0,
            variants_inspected=10,
            variants_oos=1,
            financial_loss_status=financial_status,
        ),
        findings=findings_3,
        contact_info=contact_info
    )


def test_class_a_valid_lead():
    """Verify that a genuinely eligible finding succeeds to become Class A."""
    bundle = _create_base_class_a_bundle()
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class == "A — SELLABLE"


def test_class_a_rejected_invalid_pdp_states():
    """Verify Class A is downgraded when PDP state is UNKNOWN, ERROR, or CLOUDFLARE_BLOCKED."""
    exporter = CommercialLeadExporter()
    
    for state in (PageState.UNKNOWN, PageState.ERROR, PageState.CLOUDFLARE_BLOCKED):
        bundle = _create_base_class_a_bundle(page_state=state)
        lead = exporter.assemble_lead(bundle)
        assert lead.lead_class != "A — SELLABLE"


def test_class_a_rejected_partially_inspected():
    """Verify Class A is downgraded when PDP state is PARTIALLY_INSPECTED."""
    bundle = _create_base_class_a_bundle(page_state=PageState.PARTIALLY_INSPECTED)
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class != "A — SELLABLE"


def test_class_a_rejected_detector_unknown():
    """Verify Class A is downgraded when any raw detector state is UNKNOWN."""
    exporter = CommercialLeadExporter()
    
    # Check each detector being UNKNOWN
    for detector in ["bis", "review", "upsell", "sticky"]:
        kwargs = {f"{detector}_det": "UNKNOWN"}
        bundle = _create_base_class_a_bundle(**kwargs)
        lead = exporter.assemble_lead(bundle)
        assert lead.lead_class != "A — SELLABLE"


def test_class_a_rejected_invalid_evidence():
    """Verify Class A is downgraded when evidence is invalid (valid=False)."""
    bundle = _create_base_class_a_bundle(evidence_valid=False)
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class != "A — SELLABLE"


def test_class_a_rejected_evidence_binding_mismatch():
    """Verify Class A is downgraded when finding_id does not match evidence finding_id."""
    bundle = _create_base_class_a_bundle(binding_valid=False)
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class != "A — SELLABLE"


def test_class_a_rejected_financial_status_unknown():
    """Verify Class A is downgraded when financial_loss_status is UNKNOWN."""
    bundle = _create_base_class_a_bundle(financial_status="UNKNOWN")
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class != "A — SELLABLE"


# ===========================================================================
# DEF-07 — CRO Review Selector Coverage
# ===========================================================================

def test_cro_yotpo_script_detection():
    """Verify Yotpo detection via script[src*='yotpo.com']."""
    el = DummyElement()
    page = DummyPage(elements_dict={"script[src*='yotpo.com']": el})
    detector = CROStackDetector(page)
    res = detector.detect_review_state()
    assert res.state == DetectionState.TRUE
    assert res.details == "Yotpo"


def test_cro_bazaarvoice_iframe_detection():
    """Verify Bazaarvoice detection via iframe[src*='bazaarvoice']."""
    el = DummyElement()
    page = DummyPage(elements_dict={"iframe[src*='bazaarvoice']": el})
    detector = CROStackDetector(page)
    res = detector.detect_review_state()
    assert res.state == DetectionState.TRUE
    assert res.details == "Bazaarvoice"


def test_cro_trustpilot_anchor_detection():
    """Verify Trustpilot detection via a[href*='trustpilot.com']."""
    el = DummyElement()
    page = DummyPage(elements_dict={"a[href*='trustpilot.com']": el})
    detector = CROStackDetector(page)
    res = detector.detect_review_state()
    assert res.state == DetectionState.TRUE
    assert res.details == "Trustpilot"


def test_cro_generic_review_widget_fallback():
    """Verify detection via generic review-widget selector fallbacks."""
    el = DummyElement()
    page = DummyPage(elements_dict={".product-reviews": el})
    detector = CROStackDetector(page)
    res = detector.detect_review_state()
    assert res.state == DetectionState.TRUE
    assert res.details == "Generic / Custom Review Widget"
