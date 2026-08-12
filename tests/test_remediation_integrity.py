import uuid
from unittest.mock import MagicMock, patch
from src.scanner.page_validator import PageValidator, PageState
from src.scanner.models import PDPScanResult, CommercialOpportunity, OpportunityType, EvidenceStatus
from src.scanner.detection_state import DetectionState, DetectionResult, DetectionFailureReason
from src.scanner.cro_stack_detector import CROStackDetector
from src.scanner.bis_checker import BISChecker
from src.evidence.models import Finding, VisualEvidence, BoundingBoxMap
from src.evidence.session_serializer import EvidenceBuilder
from src.commercial.lead_exporter import CommercialLeadExporter
from src.evidence.models import SessionBundle, CommercialImpact

# ==========================================
# DEF-01 — Page Validator & Cloudflare Tests
# ==========================================

def test_def01_cloudflare_blocked_by_title():
    validator = PageValidator()
    
    class MockPage:
        def title(self):
            return "Attention Required! | Cloudflare"
        def query_selector(self, selector):
            return None
        def locator(self, selector):
            mock_loc = MagicMock()
            mock_loc.inner_text.return_value = ""
            return mock_loc

    res = validator.validate_page(MockPage(), "https://example.com/products/test")
    assert res.status == PageState.CLOUDFLARE_BLOCKED
    assert res.confidence == 1.0


def test_def01_cloudflare_blocked_by_body_content():
    validator = PageValidator()

    class MockPage:
        def title(self):
            return "Access Denied"
        def query_selector(self, selector):
            return None
        def locator(self, selector):
            mock_loc = MagicMock()
            mock_loc.inner_text.return_value = "checking your browser before accessing the site."
            return mock_loc

    res = validator.validate_page(MockPage(), "https://example.com/products/test")
    assert res.status == PageState.CLOUDFLARE_BLOCKED
    assert res.confidence == 1.0


def test_def01_genuine_pdp_strong_signals():
    validator = PageValidator()

    class MockPage:
        def title(self):
            return "Awesome Shoes"
        def query_selector(self, selector):
            # Do not match Cloudflare challenge selectors
            if any(term in selector for term in ["challenge", "turnstile", "recaptcha"]):
                return None
            return MagicMock()
        def query_selector_all(self, selector):
            return []
        def evaluate(self, script):
            return True
        def locator(self, selector):
            mock_loc = MagicMock()
            mock_loc.inner_text.return_value = "Product details here"
            return mock_loc

    res = validator.validate_page(MockPage(), "https://example.com/products/shoes")
    assert res.status == PageState.REAL_PRODUCT
    assert res.confidence >= 0.8


def test_def01_ambiguous_page_returns_unknown():
    validator = PageValidator()

    class MockPage:
        def title(self):
            return "Some page"
        def query_selector(self, selector):
            return None
        def query_selector_all(self, selector):
            return []
        def evaluate(self, script):
            return False
        def locator(self, selector):
            mock_loc = MagicMock()
            mock_loc.inner_text.return_value = ""
            return mock_loc

    # Use a product-like path so it doesn't get rejected immediately by non-product regexes
    res = validator.validate_page(MockPage(), "https://example.com/products/about-us-pdp")
    assert res.status == PageState.UNKNOWN


# ==========================================
# DEF-02 — 3-State UNKNOWN Propagation Tests
# ==========================================

def test_def02_sticky_atc_insufficient_evidence():
    # If scrollHeight < 1200, must return UNKNOWN (insufficient evidence), NOT FALSE.
    class ShortPage:
        def query_selector(self, selector):
            return None
        def evaluate(self, script):
            if "scrollHeight" in script:
                return 500  # Less than 1200px
            return None

    detector = CROStackDetector(ShortPage())
    res = detector.detect_sticky_atc_state()
    assert res.state == DetectionState.UNKNOWN
    assert res.reason == DetectionFailureReason.INSUFFICIENT_EVIDENCE


def test_def02_sticky_atc_confirmed_absence():
    # If scrollHeight >= 1200 and selector absent, must return FALSE (confirmed absence)
    class TallPage:
        def query_selector(self, selector):
            return None
        def evaluate(self, script):
            if "scrollHeight" in script:
                return 1500
            if "Fixed" in script or "sticky" in script or "add" in script:
                return False
            return False

    detector = CROStackDetector(TallPage())
    res = detector.detect_sticky_atc_state()
    assert res.state == DetectionState.FALSE
    assert res.reason == DetectionFailureReason.FEATURE_ABSENT


def test_def02_reviews_insufficient_evidence_on_non_pdp():
    # Reviews absent on non-pdp -> UNKNOWN
    class NonPDPPage:
        def query_selector(self, selector):
            return None
        def query_selector_all(self, selector):
            return []
        def evaluate(self, script):
            return False

    detector = CROStackDetector(NonPDPPage())
    res = detector.detect_review_state()
    assert res.state == DetectionState.UNKNOWN
    assert res.reason == DetectionFailureReason.INSUFFICIENT_EVIDENCE


def test_def02_reviews_confirmed_absence_on_pdp():
    # Reviews absent on PDP -> FALSE
    class PDPPage:
        def query_selector(self, selector):
            if "cart" in selector or "add" in selector:
                return MagicMock()
            return None
        def query_selector_all(self, selector):
            return []
        def evaluate(self, script):
            return False

    detector = CROStackDetector(PDPPage())
    res = detector.detect_review_state()
    assert res.state == DetectionState.FALSE
    assert res.reason == DetectionFailureReason.FEATURE_ABSENT


def test_def02_bis_insufficient_evidence_on_instock():
    # BIS absent on in-stock product -> UNKNOWN
    class InStockPage:
        def query_selector(self, selector):
            return None
        def evaluate(self, script):
            return {"matched": False}

    checker = BISChecker(InStockPage())
    res = checker.check_notify_state(out_of_stock=False)
    assert res.state == DetectionState.UNKNOWN
    assert res.reason == DetectionFailureReason.INSUFFICIENT_EVIDENCE


def test_def02_bis_confirmed_absence_on_oos():
    # BIS absent on out-of-stock product -> FALSE
    class OOSPage:
        def query_selector(self, selector):
            if "sold-out" in selector or "out-of-stock" in selector:
                return MagicMock()
            return None
        def evaluate(self, script):
            return {"matched": False}

    checker = BISChecker(OOSPage())
    res = checker.check_notify_state(out_of_stock=True)
    assert res.state == DetectionState.FALSE
    assert res.reason == DetectionFailureReason.FEATURE_ABSENT


# ==========================================
# DEF-03 — Evidence ↔ PDP/Finding Binding
# ==========================================

def test_def03_evidence_finding_binding(dummy_png_bytes):
    pdp = PDPScanResult(
        product_name="Test Product",
        product_url="https://example.com/products/test",
        scanned_variant="Red",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        page_state=PageState.REAL_PRODUCT,
    )
    
    builder = EvidenceBuilder()
    finding, _, _, _, _ = builder.build_finding(
        pdp_result=pdp,
        png_bytes=dummy_png_bytes,
        bounding_boxes=BoundingBoxMap(),
        session_id=uuid.uuid4(),
    )
    
    assert str(finding.finding_id) == finding.evidence.finding_id
    assert finding.product_url == finding.evidence.pdp_url
    assert finding.evidence.store_domain == "example.com"
    assert len(finding.evidence.evidence_id) == 36


# ==========================================
# DEF-04 — Commercial Opportunity Safety Invariants
# ==========================================

def test_def04_safety_invariants_cloudflare_never_class_a():
    exporter = CommercialLeadExporter()

    # Cloudflare block page finding
    finding = Finding(
        product_name="Blocked Page",
        product_url="https://example.com/products/block",
        scanned_variant="",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        review_widget_detected=False,
        review_count=0,
        page_state=PageState.CLOUDFLARE_BLOCKED,
        opportunities=[{
            "opportunity_type": "MISSING_STICKY_ATC",
            "commercial_problem_summary": "No sticky ATC",
            "sellable_service_angle": "Sticky ATC",
            "is_valid_opportunity": True,
            "evidence_status": "VERIFIED",
        }],
        evidence=VisualEvidence(
            image_file="session_123.png",
            relative_path="https://example.com/products/block/session_123.png",
            width=1024,
            height=600,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            capture_duration_ms=450,
            browser_version="Chromium",
            valid=True,
        ),
    )

    bundle = SessionBundle(
        schema_version="2.0.0",
        scanner_version="2.3.1",
        session_id=uuid.uuid4(),
        build_id=uuid.uuid4(),
        domain="example.com",
        timestamp="2026-08-10T12:00:00Z",
        findings=[finding],
        commercial=CommercialImpact(
            est_monthly_traffic=10000,
            oos_frequency_pct=0.0,
            variants_inspected=1,
            variants_oos=0,
            est_monthly_loss_usd=0.0,
            lead_priority="LOW",
            confidence_score=0.8,
        ),
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        contact_info={"company_name": "Example", "contact_email": "hello@example.com"},
    )

    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class == "C — NOT SELLABLE"
    assert lead.manual_review_required is True
    assert lead.lead_type_category == "BLOCKED_OR_UNVERIFIED"


def test_def04_safety_invariants_unknown_never_class_a():
    exporter = CommercialLeadExporter()

    # Unknown finding
    finding = Finding(
        product_name="Unknown Page",
        product_url="https://example.com/products/unknown",
        scanned_variant="",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        review_widget_detected=False,
        review_count=0,
        page_state=PageState.UNKNOWN,
        opportunities=[{
            "opportunity_type": "MISSING_STICKY_ATC",
            "commercial_problem_summary": "No sticky ATC",
            "sellable_service_angle": "Sticky ATC",
            "is_valid_opportunity": True,
            "evidence_status": "VERIFIED",
        }],
        evidence=VisualEvidence(
            image_file="session_123.png",
            relative_path="https://example.com/products/unknown/session_123.png",
            width=1024,
            height=600,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            capture_duration_ms=450,
            browser_version="Chromium",
            valid=True,
        ),
    )

    bundle = SessionBundle(
        schema_version="2.0.0",
        scanner_version="2.3.1",
        session_id=uuid.uuid4(),
        build_id=uuid.uuid4(),
        domain="example.com",
        timestamp="2026-08-10T12:00:00Z",
        findings=[finding],
        commercial=CommercialImpact(
            est_monthly_traffic=10000,
            oos_frequency_pct=0.0,
            variants_inspected=1,
            variants_oos=0,
            est_monthly_loss_usd=0.0,
            lead_priority="LOW",
            confidence_score=0.8,
        ),
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        contact_info={"company_name": "Example", "contact_email": "hello@example.com"},
    )

    lead = exporter.assemble_lead(bundle)
    assert lead.lead_class == "B — USABLE WITH CAUTION"
    assert lead.manual_review_required is True
    assert lead.lead_type_category == "BLOCKED_OR_UNVERIFIED"
