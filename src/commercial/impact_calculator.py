"""
src/commercial/impact_calculator.py — Pure Commercial Impact & Financial Loss Calculator

Layer 3: Commercial Intelligence Engine
"""
import logging
from typing import Any

from src.config import (
    DEFAULT_AOV_FALLBACK_USD,
    DEFAULT_BASELINE_CONVERSION_RATE,
    DEFAULT_TRAFFIC_FALLBACK_VISITS,
)
from src.evidence.models import CommercialImpact
from src.commercial.models import (
    CommercialCalculationResult,
    CommercialParameterProvenance,
    ParameterSource,
)
from src.scanner.models import TransientScanContext

logger = logging.getLogger(__name__)


class CommercialImpactCalculator:
    """
    Pure, deterministic financial loss calculator.
    
    Formula:
      Est. Monthly Lost Revenue ($) = Monthly Traffic * OOS Ratio * Baseline CR * AOV
    
    DOES NOT:
      - Use Playwright / DOM selectors
      - Call external APIs or HTTP services
      - Write SessionBundle or call SessionStorage
      - Render PDFs, Teasers, or HTML
      - Import V1 legacy code
    """

    def __init__(
        self,
        default_baseline_cr: float = DEFAULT_BASELINE_CONVERSION_RATE,
        default_aov_fallback: float = DEFAULT_AOV_FALLBACK_USD,
        default_traffic_fallback: int = DEFAULT_TRAFFIC_FALLBACK_VISITS,
    ) -> None:
        self.default_baseline_cr = default_baseline_cr
        self.default_aov_fallback = default_aov_fallback
        self.default_traffic_fallback = default_traffic_fallback

    def compute_impact(
        self,
        scan_context: TransientScanContext,
        measured_traffic: int | None = None,
        traffic_source_name: str | None = None,
    ) -> CommercialCalculationResult:
        """
        Computes commercial financial impact, parameter provenance, lead priority, and confidence score.
        Accepts transient scan findings from Phase B.
        """
        provenance: list[CommercialParameterProvenance] = []
        confidence_score = 1.0
        has_fallback = False

        # 1. Aggregate OOS Ratio & Sample Density from TransientScanContext
        total_inspected = 0
        total_oos = 0
        extracted_prices: list[float] = []

        for pdp in scan_context.pdp_results:
            total_inspected += pdp.variants_inspected
            if pdp.out_of_stock:
                total_oos += max(pdp.variants_oos, 1)
            # Gather prices
            if hasattr(pdp, "inspected_prices") and pdp.inspected_prices:
                extracted_prices.extend(pdp.inspected_prices)

        # Handle division by zero safely (DEF-08 Fix: Do NOT generate false loss when 0 variants inspected)
        if total_inspected == 0:
            oos_ratio = 0.0
            oos_frequency_pct = 0.0
            has_fallback = True
            provenance.append(
                CommercialParameterProvenance(
                    parameter_name="oos_ratio",
                    value=0.0,
                    source=ParameterSource.FALLBACK_ASSUMED,
                    source_detail="Zero variants inspected in sample (OOS ratio set to 0.0%)",
                    confidence_impact=-0.1,
                )
            )
            confidence_score -= 0.1
        else:
            oos_ratio = total_oos / total_inspected
            # Clamp ratio to [0.0, 1.0]
            oos_ratio = max(0.0, min(1.0, oos_ratio))
            oos_frequency_pct = round(oos_ratio * 100.0, 4)
            provenance.append(
                CommercialParameterProvenance(
                    parameter_name="oos_ratio",
                    value=oos_ratio,
                    source=ParameterSource.PRIMARY_MEASURED,
                    source_detail=f"Measured sample density ({total_oos} OOS / {total_inspected} inspected variants)",
                    confidence_impact=0.0,
                )
            )

        # 2. Process Monthly Traffic Parameter
        if measured_traffic is not None and measured_traffic > 0:
            traffic = measured_traffic
            provenance.append(
                CommercialParameterProvenance(
                    parameter_name="monthly_traffic",
                    value=traffic,
                    source=ParameterSource.PRIMARY_MEASURED,
                    source_detail=f"Primary measurement via {traffic_source_name or 'Traffic Provider'}",
                    confidence_impact=0.0,
                )
            )
        else:
            traffic = self.default_traffic_fallback
            has_fallback = True
            confidence_score -= 0.3  # Mandatory -0.3 penalty for traffic fallback
            provenance.append(
                CommercialParameterProvenance(
                    parameter_name="monthly_traffic",
                    value=traffic,
                    source=ParameterSource.FALLBACK_ASSUMED,
                    source_detail=f"Category Median Tier Fallback ({traffic:,} visits/mo)",
                    confidence_impact=-0.3,
                )
            )

        # 3. Process Baseline Conversion Rate Parameter
        baseline_cr = self.default_baseline_cr
        provenance.append(
            CommercialParameterProvenance(
                parameter_name="baseline_cr",
                value=baseline_cr,
                source=ParameterSource.FALLBACK_ASSUMED,
                source_detail=f"Standard Category Benchmark ({baseline_cr * 100:.1f}%)",
                confidence_impact=0.0,
            )
        )

        # 4. Process Average Order Value (AOV) Parameter
        if extracted_prices:
            aov = sum(extracted_prices) / len(extracted_prices)
            provenance.append(
                CommercialParameterProvenance(
                    parameter_name="aov_usd",
                    value=round(aov, 2),
                    source=ParameterSource.PRIMARY_MEASURED,
                    source_detail=f"Extracted PDP product price average (${aov:.2f})",
                    confidence_impact=0.0,
                )
            )
        else:
            aov = self.default_aov_fallback
            has_fallback = True
            provenance.append(
                CommercialParameterProvenance(
                    parameter_name="aov_usd",
                    value=aov,
                    source=ParameterSource.FALLBACK_ASSUMED,
                    source_detail=f"Category Median AOV Fallback (${aov:.2f} USD)",
                    confidence_impact=-0.05,
                )
            )
            confidence_score -= 0.05

        # 5. Financial Loss Calculation
        # Formula: Est. Monthly Lost Revenue ($) = Traffic * OOS Ratio * Baseline CR * AOV
        est_monthly_loss_usd = round(traffic * oos_ratio * baseline_cr * aov, 2)

        # Mandatory Fallback Disclosure Lock:
        # If ANY fallback is used, confidence_score MUST be < 0.70
        if has_fallback and confidence_score >= 0.70:
            confidence_score = 0.69

        # Clamp confidence score to [0.0, 1.0]
        confidence_score = max(0.0, min(1.0, round(confidence_score, 2)))

        # 6. Determine Agency Lead Priority
        # HIGH: >= $10,000/mo loss | MEDIUM: $2,500-$9,999/mo | LOW: < $2,500/mo
        if est_monthly_loss_usd >= 10000.0:
            lead_priority = "HIGH"
        elif est_monthly_loss_usd >= 2500.0:
            lead_priority = "MEDIUM"
        else:
            lead_priority = "LOW"

        # 7. Construct Footnote Disclosure Statement
        if has_fallback:
            footnote = (
                f"* Note: Revenue loss estimation includes benchmark parameters "
                f"(Confidence Rating: {confidence_score * 100:.0f}%). "
                f"Traffic estimated at {traffic:,} visits/mo; AOV estimated at ${aov:.2f}."
            )
        else:
            footnote = (
                f"* Estimated based on measured PDP out-of-stock ratio ({oos_frequency_pct:.1f}%) "
                f"and measured monthly traffic ({traffic:,} visits/mo)."
            )

        if total_inspected == 0:
            financial_loss_status = "UNKNOWN"
        elif measured_traffic is not None and measured_traffic > 0 and len(extracted_prices) > 0:
            financial_loss_status = "VERIFIED"
        else:
            financial_loss_status = "ESTIMATED"

        return CommercialCalculationResult(
            est_monthly_traffic=traffic,
            oos_frequency_pct=oos_frequency_pct,
            variants_inspected=total_inspected,
            variants_oos=total_oos,
            baseline_cr=baseline_cr,
            aov_usd=aov,
            est_monthly_loss_usd=est_monthly_loss_usd,
            lead_priority=lead_priority,
            confidence_score=confidence_score,
            has_fallback_parameters=has_fallback,
            provenance_records=provenance,
            footnote_disclosure=footnote,
            financial_loss_status=financial_loss_status,
        )

    def build_commercial_impact_dto(
        self,
        scan_context: TransientScanContext,
        measured_traffic: int | None = None,
        traffic_source_name: str | None = None,
    ) -> CommercialImpact:
        """
        Helper returning a validated Phase A CommercialImpact DTO directly.
        """
        res = self.compute_impact(scan_context, measured_traffic, traffic_source_name)
        return CommercialImpact(
            est_monthly_traffic=res.est_monthly_traffic,
            oos_frequency_pct=res.oos_frequency_pct,
            variants_inspected=res.variants_inspected,
            variants_oos=res.variants_oos,
            est_monthly_loss_usd=res.est_monthly_loss_usd,
            lead_priority=res.lead_priority,
            confidence_score=res.confidence_score,
            financial_loss_status=res.financial_loss_status,
        )
