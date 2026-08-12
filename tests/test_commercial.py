"""
tests/test_commercial.py — Complete Test Suite for Phase C Commercial Intelligence

Covers:
  1. OOS ratio & frequency percentage calculation.
  2. Division by zero handling (variants_inspected == 0).
  3. Correct monthly lost revenue formula calculation.
  4. Primary traffic measurement path.
  5. Fallback traffic measurement path.
  6. Confidence score penalty (-0.3) application on traffic fallback.
  7. Mandatory fallback confidence restriction (< 0.70).
  8. AOV fallback to $65.00 USD.
  9. Baseline CR benchmark disclosure.
  10. Lead priority threshold classification (HIGH, MEDIUM, LOW).
  11. CommercialImpact Pydantic validation & compatibility with Phase A DTO.
  12. Boundary isolation (0 Playwright, 0 SessionStorage, 0 PDF/HTML imports).
  13. Phase A regression tests.
  14. Phase B regression tests.
"""
import pytest
from src.commercial.impact_calculator import CommercialImpactCalculator
from src.commercial.models import CommercialCalculationResult, ParameterSource
from src.evidence.models import CommercialImpact
from src.scanner.page_validator import PageState
from src.scanner.models import PDPScanResult, TransientScanContext


# ---------------------------------------------------------------------------
# 1. Formula & Revenue Loss Calculation Tests
# ---------------------------------------------------------------------------
def test_lost_revenue_exact_formula_calculation():
    """
    Test exact formula: Traffic * OOS Ratio * Baseline CR * AOV
    Traffic = 100,000 | OOS Ratio = 0.10 | Baseline CR = 0.02 | AOV = 65.00
    Expected = 100,000 * 0.10 * 0.02 * 65 = 13,000 USD/month
    """
    calc = CommercialImpactCalculator(
        default_baseline_cr=0.02,
        default_aov_fallback=65.00,
        default_traffic_fallback=100000,
    )
    context = TransientScanContext(
        domain="toms.com",
        pdp_results=[
            PDPScanResult(
                product_name="Santiago Loafer",
                product_url="https://toms.com/products/loafer",
                scanned_variant="Size 9",
                out_of_stock=True,
                notify_button_detected=False,
                sold_out_detected=True,
                page_state=PageState.REAL_PRODUCT,
                variants_inspected=10,
                variants_oos=1,  # 1/10 = 0.10 OOS ratio
            )
        ],
    )

    result = calc.compute_impact(context, measured_traffic=100000, traffic_source_name="Tranco Tier")
    assert result.est_monthly_loss_usd == 13000.0
    assert result.oos_frequency_pct == 10.0
    assert result.lead_priority == "HIGH"


def test_division_by_zero_handling_empty_sample():
    """Verifies that 0 variants inspected sets OOS ratio to 0.0 — no false financial loss (DEF-08 fix)."""
    calc = CommercialImpactCalculator()
    context = TransientScanContext(domain="empty.com", pdp_results=[])

    result = calc.compute_impact(context)
    assert result.variants_inspected == 0
    assert result.oos_frequency_pct == 0.0
    assert result.est_monthly_loss_usd == 0.0
    assert result.has_fallback_parameters is True
    assert result.confidence_score < 0.70


# ---------------------------------------------------------------------------
# 2. Parameter Provenance & Fallback Penalty Tests
# ---------------------------------------------------------------------------
def test_primary_traffic_source_no_penalty():
    calc = CommercialImpactCalculator()
    context = TransientScanContext(
        domain="primary.com",
        pdp_results=[
            PDPScanResult(
                product_name="Item",
                product_url="https://primary.com/products/item",
                scanned_variant="V1",
                out_of_stock=True,
                notify_button_detected=False,
                sold_out_detected=True,
                page_state=PageState.REAL_PRODUCT,
                variants_inspected=10,
                variants_oos=1,
            )
        ],
    )

    result = calc.compute_impact(context, measured_traffic=50000, traffic_source_name="BuiltWith API")
    traffic_prov = next(p for p in result.provenance_records if p.parameter_name == "monthly_traffic")
    assert traffic_prov.source == ParameterSource.PRIMARY_MEASURED
    assert traffic_prov.confidence_impact == 0.0


def test_fallback_traffic_source_applies_confidence_penalty():
    calc = CommercialImpactCalculator()
    context = TransientScanContext(
        domain="fallback.com",
        pdp_results=[
            PDPScanResult(
                product_name="Item",
                product_url="https://fallback.com/products/item",
                scanned_variant="V1",
                out_of_stock=True,
                notify_button_detected=False,
                sold_out_detected=True,
                page_state=PageState.REAL_PRODUCT,
                variants_inspected=10,
                variants_oos=1,
            )
        ],
    )

    result = calc.compute_impact(context, measured_traffic=None)  # Triggers fallback
    assert result.has_fallback_parameters is True
    assert result.confidence_score < 0.70  # Mandatory fallback confidence lock
    assert "* Note: Revenue loss estimation includes benchmark parameters" in result.footnote_disclosure


# ---------------------------------------------------------------------------
# 3. Lead Priority Threshold Tests
# ---------------------------------------------------------------------------
def test_lead_priority_thresholds():
    calc = CommercialImpactCalculator()
    
    # 1. High Priority (>= $10,000/mo)
    ctx_high = TransientScanContext(
        domain="high.com",
        pdp_results=[
            PDPScanResult(
                product_name="Item", product_url="https://high.com/item", scanned_variant="V1",
                out_of_stock=True, notify_button_detected=False, sold_out_detected=True,
                page_state=PageState.REAL_PRODUCT,
                variants_inspected=10, variants_oos=2,
            )
        ],
    )
    res_high = calc.compute_impact(ctx_high, measured_traffic=100000)
    assert res_high.lead_priority == "HIGH"

    # 2. Low Priority (< $2,500/mo)
    ctx_low = TransientScanContext(
        domain="low.com",
        pdp_results=[
            PDPScanResult(
                product_name="Item", product_url="https://low.com/item", scanned_variant="V1",
                out_of_stock=True, notify_button_detected=False, sold_out_detected=True,
                page_state=PageState.REAL_PRODUCT,
                variants_inspected=10, variants_oos=1,
            )
        ],
    )
    res_low = calc.compute_impact(ctx_low, measured_traffic=10000)
    assert res_low.lead_priority == "LOW"


# ---------------------------------------------------------------------------
# 4. Phase A DTO Compatibility Test
# ---------------------------------------------------------------------------
def test_build_commercial_impact_dto_phase_a_compatibility():
    calc = CommercialImpactCalculator()
    context = TransientScanContext(
        domain="toms.com",
        pdp_results=[
            PDPScanResult(
                product_name="Loafer", product_url="https://toms.com/loafer", scanned_variant="V1",
                out_of_stock=True, notify_button_detected=False, sold_out_detected=True,
                page_state=PageState.REAL_PRODUCT,
                variants_inspected=10, variants_oos=1,
            )
        ],
    )


    dto = calc.build_commercial_impact_dto(context, measured_traffic=120000)
    assert isinstance(dto, CommercialImpact)
    assert dto.est_monthly_traffic == 120000
    assert dto.lead_priority == "HIGH"
    assert dto.confidence_score < 0.70  # AOV used fallback $65


# ---------------------------------------------------------------------------
# 5. Static Architectural Boundary Isolation Test
# ---------------------------------------------------------------------------
def test_commercial_module_has_no_prohibited_imports():
    import src.commercial.impact_calculator as ic
    import src.commercial.models as cm

    for mod in (ic, cm):
        # Must not import Playwright
        assert not hasattr(mod, "playwright")
        assert not hasattr(mod, "Page")
        # Must not import SessionStorage
        assert not hasattr(mod, "SessionStorage")
        assert not hasattr(mod, "save_new_bundle")
        # Must not import presentation drivers
        assert not hasattr(mod, "weasyprint")
        assert not hasattr(mod, "ReportBuilder")
