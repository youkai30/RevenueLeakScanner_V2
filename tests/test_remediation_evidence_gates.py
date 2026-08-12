"""
tests/test_remediation_evidence_gates.py — Regression tests for visual-DOM overlay gates and Sticky ATC check.
"""
import uuid
import shutil
import pytest
from pathlib import Path
from src.scanner.models import PDPScanResult, CommercialOpportunity, OpportunityType, PageState, TransientScanContext
from src.scanner.cro_stack_detector import CROStackDetector
from src.scanner.detection_state import DetectionState
from src.evidence.session_serializer import EvidenceBuilder
from src.evidence.session_storage import SessionStorage
from src.evidence.models import SessionBundle, CommercialImpact, BoundingBoxMap, Finding
from src.commercial.lead_exporter import CommercialLeadExporter
from src.config import SESSIONS_DIR

class FakePage:
    def __init__(self, scroll_height=1500, has_sticky_purchase=False, has_unresolved_modal=False):
        self.scroll_height = scroll_height
        self.has_sticky_purchase = has_sticky_purchase
        self.has_unresolved_modal = has_unresolved_modal
        self.keyboard = self
        self.scrolls = []
        self.waits = []

    def press(self, key):
        pass

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    def evaluate(self, script, *args):
        if "scrollTo" in script:
            self.scrolls.append(script)
            return None
        if "scrollHeight" in script:
            return self.scroll_height
        if "has_sticky_purchase" in script or "els.some" in script:
            return self.has_sticky_purchase
        if "has_unresolved_modal" in script or "role=\"dialog\"" in script:
            return self.has_unresolved_modal
        return None

    def query_selector(self, selector):
        return None


def test_gate_a_overlay_blocks_pdp(tmp_path):
    """Test A: If unresolved modal is True, evidence.valid must be False."""
    pdp = PDPScanResult(
        product_name="Blocked Product",
        product_url="https://testevidencegates.com/products/blocked",
        scanned_variant="Default",
        out_of_stock=False,
        page_state=PageState.REAL_PRODUCT,
        has_unresolved_modal=True,  # Blocking overlay!
        notify_button_detected=False,
        sold_out_detected=False
    )
    
    # Generate 1024x600 minimal PNG bytes
    from PIL import Image
    from io import BytesIO
    img = Image.new("RGBA", (1024, 600), "white")
    img.putpixel((0, 0), (0, 0, 0, 255))
    out = BytesIO()
    img.save(out, format="PNG")
    png_bytes = out.getvalue()

    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)
    
    finding, _, _, _, _ = builder.build_finding(
        pdp_result=pdp,
        png_bytes=png_bytes,
        bounding_boxes=BoundingBoxMap(),
        session_id=uuid.uuid4(),
    )
    
    # Evidence must be invalid
    assert finding.evidence.valid is False
    assert "Unresolved modal overlay" in finding.evidence.validation_reason


def test_gate_b_sticky_atc_behavioral_present():
    """Test B: Sticky ATC is present after scroll."""
    page = FakePage(scroll_height=1500, has_sticky_purchase=True)
    detector = CROStackDetector(page)
    result = detector.detect_sticky_atc_state()
    
    assert result.state == DetectionState.TRUE
    assert "style check confirmed presence" in result.details
    assert len(page.scrolls) > 0  # Page scrolled down!


def test_gate_c_sticky_atc_unknown():
    """Test C: Sticky ATC is unknown when page mock cannot scroll or is invalid."""
    class BadFakePage:
        pass  # Lacks evaluate/query_selector
    
    detector = CROStackDetector(BadFakePage())
    result = detector.detect_sticky_atc_state()
    assert result.state == DetectionState.UNKNOWN


def test_gate_d_screenshot_contradiction():
    """Test D: If screenshot evidence is invalid, lead cannot be Class A (must be Class B or C)."""
    domain = "testevidencegatesd.com"
    shutil.rmtree(SESSIONS_DIR / domain, ignore_errors=True)

    pdp = PDPScanResult(
        product_name="Product D",
        product_url=f"https://{domain}/products/d",
        scanned_variant="Default",
        out_of_stock=False,
        page_state=PageState.REAL_PRODUCT,
        has_unresolved_modal=True,  # Modal block!
        notify_button_detected=False,
        sold_out_detected=False,
        opportunities=[
            CommercialOpportunity(
                opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                commercial_problem_summary="Missing Sticky ATC",
                sellable_service_angle="Sticky ATC Optimization"
            )
        ]
    )

    from PIL import Image
    from io import BytesIO
    img = Image.new("RGBA", (1024, 600), "white")
    img.putpixel((0, 0), (0, 0, 0, 255))
    out = BytesIO()
    img.save(out, format="PNG")
    png_bytes = out.getvalue()

    storage = SessionStorage()
    builder = EvidenceBuilder(storage=storage)
    
    session_id = uuid.uuid4()
    commercial = CommercialImpact(
        est_monthly_loss_usd=100.0,
        est_monthly_traffic=5000,
        lead_priority="MEDIUM",
        confidence_score=0.8,
        variants_inspected=1,
        variants_oos=0,
        financial_loss_status="ESTIMATED",
        oos_frequency_pct=0.0
    )
    
    bundle = builder.compile_and_save_session(
        domain=domain,
        transient_context=TransientScanContext(domain=domain, pdp_results=[pdp]),
        commercial_impact=commercial,
        pdp_evidence_items=[(pdp, png_bytes, BoundingBoxMap())],
        session_id=session_id
    )

    exporter = CommercialLeadExporter()
    lead_record = exporter.assemble_lead(bundle)
    
    # Lead must NOT be Class A
    assert lead_record.lead_class != "A — SELLABLE"

    shutil.rmtree(SESSIONS_DIR / domain, ignore_errors=True)


def test_gate_e_clean_missing_feature():
    """Test E: Clean page + confirmed missing feature -> Finding = valid, Evidence = valid."""
    domain = "testevidencegatese.com"
    shutil.rmtree(SESSIONS_DIR / domain, ignore_errors=True)

    pdp = PDPScanResult(
        product_name="Product E",
        product_url=f"https://{domain}/products/e",
        scanned_variant="Default",
        out_of_stock=False,
        page_state=PageState.REAL_PRODUCT,
        has_unresolved_modal=False,  # Clean page!
        notify_button_detected=False,
        sold_out_detected=False,
        opportunities=[
            CommercialOpportunity(
                opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                commercial_problem_summary="Missing Sticky ATC",
                sellable_service_angle="Sticky ATC Optimization"
            )
        ]
    )

    from PIL import Image
    from io import BytesIO
    img = Image.new("RGBA", (1024, 600), "white")
    img.putpixel((0, 0), (0, 0, 0, 255))
    out = BytesIO()
    img.save(out, format="PNG")
    png_bytes = out.getvalue()

    storage = SessionStorage()
    builder = EvidenceBuilder(storage=storage)
    
    session_id = uuid.uuid4()
    commercial = CommercialImpact(
        est_monthly_loss_usd=100.0,
        est_monthly_traffic=5000,
        lead_priority="MEDIUM",
        confidence_score=0.8,
        variants_inspected=1,
        variants_oos=0,
        financial_loss_status="ESTIMATED",
        oos_frequency_pct=0.0
    )
    
    transient_context = TransientScanContext(domain=domain, pdp_results=[pdp])
    transient_context.metadata["contact_info"] = {"email": "contact@test.com", "email_source": "MAILTO"}

    bundle = builder.compile_and_save_session(
        domain=domain,
        transient_context=transient_context,
        commercial_impact=commercial,
        pdp_evidence_items=[(pdp, png_bytes, BoundingBoxMap())],
        session_id=session_id
    )

    # Verify Finding and Evidence are valid (Test E requirements)
    assert len(bundle.findings) == 1
    finding = bundle.findings[0]
    assert finding.evidence.valid is True
    assert finding.evidence.validation_reason == "OK"

    shutil.rmtree(SESSIONS_DIR / domain, ignore_errors=True)
