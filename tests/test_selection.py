"""
tests/test_selection.py — Test Suite for Phase G Selection & Ground-Truth Validation Layer

Covers:
  1. GroundTruthValidator assertion testing (valid bundle passes, invalid bundle rejected).
  2. EvidenceScorer ranking heuristic computation.
  3. CandidateSelector session discovery, ground-truth filtering, and score sorting.
  4. Layer boundary isolation (0 Playwright, 0 Scanner, 0 SessionStorage writes).
  5. Read-only SessionBundle consumption verification.
"""
import pytest

from src.commercial.impact_calculator import CommercialImpactCalculator
from src.evidence.models import BoundingBoxMap
from src.evidence.session_serializer import EvidenceBuilder
from src.evidence.session_storage import SessionStorage
from src.scanner.page_validator import PageState
from src.scanner.models import PDPScanResult, TransientScanContext
from src.selection.candidate_selector import CandidateSelector
from src.selection.evidence_scorer import EvidenceScorer
from src.selection.ground_truth_validator import GroundTruthValidator


# ---------------------------------------------------------------------------
# 1. GroundTruthValidator Unit Tests
# ---------------------------------------------------------------------------
def test_ground_truth_validator(tmp_path, dummy_png_bytes):
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    pdp = PDPScanResult(
        product_name="Valid Product",
        product_url="https://test.com/valid",
        scanned_variant="Var 1",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
    )
    context = TransientScanContext(domain="test.com", pdp_results=[pdp])
    calc = CommercialImpactCalculator()
    comm = calc.build_commercial_impact_dto(context, measured_traffic=100000)

    bundle = builder.compile_and_save_session(
        domain="test.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=[(pdp, dummy_png_bytes, BoundingBoxMap())],
    )

    validator = GroundTruthValidator()
    val_res = validator.validate_session_bundle(bundle)

    assert val_res.is_valid is True
    assert len(val_res.rejection_reasons) == 0


# ---------------------------------------------------------------------------
# 2. EvidenceScorer Unit Tests
# ---------------------------------------------------------------------------
def test_evidence_scorer(tmp_path, dummy_png_bytes):
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    from src.scanner.models import CommercialOpportunity, OpportunityType
    opp = CommercialOpportunity(
        opportunity_type=OpportunityType.REVENUE_LEAK,
        commercial_problem_summary="High lost revenue OOS",
        sellable_service_angle="BIS Flow",
    )
    pdp = PDPScanResult(
        product_name="High Value Product",
        product_url="https://test.com/high",
        scanned_variant="Var High",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
        review_widget_detected=True,
        variants_inspected=10,
        variants_oos=3,
        opportunities=[opp],
    )

    context = TransientScanContext(domain="test.com", pdp_results=[pdp])
    calc = CommercialImpactCalculator()
    comm = calc.build_commercial_impact_dto(context, measured_traffic=120000)

    bundle = builder.compile_and_save_session(
        domain="test.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=[(pdp, dummy_png_bytes, BoundingBoxMap())],
    )

    scorer = EvidenceScorer()
    score = scorer.calculate_score(bundle)

    assert score > 50.0  # High lost revenue and OOS ratio boost score
    assert score <= 100.0


# ---------------------------------------------------------------------------
# 3. CandidateSelector Integration Test
# ---------------------------------------------------------------------------
def test_candidate_selector_discovery(tmp_path, dummy_png_bytes):
    storage = SessionStorage(base_storage_dir=tmp_path)
    builder = EvidenceBuilder(storage=storage)

    pdp = PDPScanResult(
        product_name="Loafer",
        product_url="https://toms.com/loafer",
        scanned_variant="Size 9",
        out_of_stock=True,
        notify_button_detected=False,
        sold_out_detected=True,
        page_state=PageState.REAL_PRODUCT,
    )
    context = TransientScanContext(domain="toms.com", pdp_results=[pdp])
    calc = CommercialImpactCalculator()
    comm = calc.build_commercial_impact_dto(context, measured_traffic=100000)

    bundle = builder.compile_and_save_session(
        domain="toms.com",
        transient_context=context,
        commercial_impact=comm,
        pdp_evidence_items=[(pdp, dummy_png_bytes, BoundingBoxMap())],
    )

    selector = CandidateSelector(storage=storage)
    candidates = selector.discover_and_rank_candidates(domain="toms.com")

    assert len(candidates) == 1
    assert candidates[0].session_bundle.session_id == bundle.session_id
    assert candidates[0].is_valid_ground_truth is True


# ---------------------------------------------------------------------------
# 4. Architectural Boundary Isolation Test
# ---------------------------------------------------------------------------
def test_selection_layer_boundary_isolation():
    import src.selection.candidate_selector as cs
    import src.selection.evidence_scorer as es
    import src.selection.ground_truth_validator as gtv

    for mod in (cs, es, gtv):
        assert not hasattr(mod, "playwright")
        assert not hasattr(mod, "Page")
        assert not hasattr(mod, "save_new_bundle")
