"""
src/commercial/impact_calculator.py — Multi-Opportunity Commercial Impact Calculator

Layer 3: Commercial Intelligence Engine

P4: Evaluates ALL commercial opportunities (not just OOS):
    - REVENUE_LEAK: traffic × oos_ratio × CR × AOV
    - MISSING_SOCIAL_PROOF: traffic × uplift_7% × CR × AOV × coverage_0.3
    - MISSING_UPSELL: traffic × uplift_15% × AOV × margin_0.3 × coverage_0.4
    - MISSING_STICKY_ATC: mobile_traffic × uplift_10% × CR × AOV

DOES NOT:
  - Use Playwright / DOM selectors
  - Call external APIs or HTTP services
  - Write SessionBundle or call SessionStorage
  - Render PDFs, Teasers, or HTML
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
from src.scanner.models import TransientScanContext, OpportunityType

logger = logging.getLogger(__name__)

# P4 — Opportunity-specific uplift constants (from CRO research)
OPPORTUNITY_UPLIFTS = {
    "REVENUE_LEAK": {
        "base_formula": "traffic × oos_ratio × CR × AOV",
        "uplift_pct": None,  # Uses actual OOS ratio
        "coverage": 1.0,
    },
    "MISSING_SOCIAL_PROOF": {
        "base_formula": "traffic × uplift × CR × AOV × coverage",
        "uplift_pct": 0.07,   # 7% conversion uplift (CXL Institute)
        "coverage": 0.30,     # 30% of visitors see buy box
    },
    "MISSING_UPSELL": {
        "base_formula": "traffic × uplift × AOV × margin × coverage",
        "uplift_pct": 0.15,   # 15% AOV uplift (McKinsey)
        "coverage": 0.40,     # 40% of buyers see upsell
        "margin_factor": 0.30, # 30% gross margin
    },
    "MISSING_STICKY_ATC": {
        "base_formula": "mobile_traffic × uplift × CR × AOV",
        "uplift_pct": 0.10,   # 10% conversion uplift (Baymard)
        "coverage": 1.0,
        "mobile_share": 0.55, # 55% mobile traffic (Statista 2024)
    },
}


class CommercialImpactCalculator:
    """
    Pure, deterministic financial loss calculator supporting multiple opportunity types.
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

    def _count_opportunities(self, scan_context: TransientScanContext) -> dict[str, int]:
        """Count occurrences of each opportunity type across all PDPs."""
        counts: dict[str, int] = {
            "REVENUE_LEAK": 0,
            "MISSING_SOCIAL_PROOF": 0,
            "MISSING_UPSELL": 0,
            "MISSING_STICKY_ATC": 0,
        }
        for pdp in scan_context.pdp_results:
            for opp in pdp.opportunities:
                opp_type = opp.opportunity_type.value if hasattr(opp.opportunity_type, "value") else str(opp.opportunity_type)
                if opp_type in counts:
                    counts[opp_type] += 1
        return counts

    def compute_impact(
        self,
        scan_context: TransientScanContext,
        measured_traffic: int | None = None,
        traffic_source_name: str | None = None,
    ) -> CommercialCalculationResult:
        """
        Computes commercial financial impact across ALL opportunity types.
        Returns total loss = REVENUE_LEAK + SOCIAL_PROOF + UPSELL + STICKY_ATC.
        """
        provenance: list[CommercialParameterProvenance] = []
        confidence_score = 1.0
        has_fallback = False

        # 1. Aggregate OOS Ratio & Sample Density
        total_inspected = 0
        total_oos = 0
        extracted_prices: list[float] = []

        for pdp in scan_context.pdp_results:
            total_inspected += pdp.variants_inspected
            if pdp.out_of_stock:
                total_oos += max(pdp.variants_oos, 1)
            if hasattr(pdp, "inspected_prices") and pdp.inspected_prices:
                extracted_prices.extend(pdp.inspected_prices)

        if total_inspected == 0:
            oos_ratio = 0.0
            oos_frequency_pct = 0.0
            has_fallback = True
            provenance.append(CommercialParameterProvenance(
                parameter_name="oos_ratio",
                value=0.0,
                source=ParameterSource.FALLBACK_ASSUMED,
                source_detail="Zero variants inspected (OOS ratio = 0.0%)",
                confidence_impact=-0.1,
            ))
            confidence_score -= 0.1
        else:
            oos_ratio = max(0.0, min(1.0, total_oos / total_inspected))
            oos_frequency_pct = round(oos_ratio * 100.0, 4)
            provenance.append(CommercialParameterProvenance(
                parameter_name="oos_ratio",
                value=oos_ratio,
                source=ParameterSource.PRIMARY_MEASURED,
                source_detail=f"Measured ({total_oos} OOS / {total_inspected} variants)",
                confidence_impact=0.0,
            ))

        # 2. Traffic
        if measured_traffic is not None and measured_traffic > 0:
            traffic = measured_traffic
            provenance.append(CommercialParameterProvenance(
                parameter_name="monthly_traffic",
                value=traffic,
                source=ParameterSource.PRIMARY_MEASURED,
                source_detail=f"Primary measurement via {traffic_source_name or 'Traffic Provider'}",
                confidence_impact=0.0,
            ))
        else:
            traffic = self.default_traffic_fallback
            has_fallback = True
            confidence_score -= 0.3
            provenance.append(CommercialParameterProvenance(
                parameter_name="monthly_traffic",
                value=traffic,
                source=ParameterSource.FALLBACK_ASSUMED,
                source_detail=f"Category Median ({traffic:,} visits/mo)",
                confidence_impact=-0.3,
            ))

        # 3. Baseline CR
        baseline_cr = self.default_baseline_cr
        provenance.append(CommercialParameterProvenance(
            parameter_name="baseline_cr",
            value=baseline_cr,
            source=ParameterSource.FALLBACK_ASSUMED,
            source_detail=f"Standard Benchmark ({baseline_cr * 100:.1f}%)",
            confidence_impact=0.0,
        ))

        # 4. AOV
        if extracted_prices:
            aov = sum(extracted_prices) / len(extracted_prices)
            provenance.append(CommercialParameterProvenance(
                parameter_name="aov_usd",
                value=round(aov, 2),
                source=ParameterSource.PRIMARY_MEASURED,
                source_detail=f"Extracted PDP price avg (${aov:.2f})",
                confidence_impact=0.0,
            ))
        else:
            aov = self.default_aov_fallback
            has_fallback = True
            provenance.append(CommercialParameterProvenance(
                parameter_name="aov_usd",
                value=aov,
                source=ParameterSource.FALLBACK_ASSUMED,
                source_detail=f"Category Median AOV (${aov:.2f})",
                confidence_impact=-0.05,
            ))
            confidence_score -= 0.05

        # ─────────────────────────────────────────────────────────────
        # 5. P4: Multi-Opportunity Financial Loss Calculation
        # ─────────────────────────────────────────────────────────────
        opp_counts = self._count_opportunities(scan_context)
        total_loss = 0.0
        breakdown: dict[str, float] = {}

        # REVENUE_LEAK: traffic × oos_ratio × CR × AOV
        if opp_counts["REVENUE_LEAK"] > 0:
            leak = traffic * oos_ratio * baseline_cr * aov
            total_loss += leak
            breakdown["REVENUE_LEAK"] = round(leak, 2)

        # MISSING_SOCIAL_PROOF: traffic × 7% uplift × CR × AOV × 0.3
        if opp_counts["MISSING_SOCIAL_PROOF"] > 0:
            uplift = OPPORTUNITY_UPLIFTS["MISSING_SOCIAL_PROOF"]["uplift_pct"]
            coverage = OPPORTUNITY_UPLIFTS["MISSING_SOCIAL_PROOF"]["coverage"]
            sp = traffic * uplift * baseline_cr * aov * coverage
            total_loss += sp
            breakdown["MISSING_SOCIAL_PROOF"] = round(sp, 2)

        # MISSING_UPSELL: traffic × 15% uplift × AOV × 30% margin × 0.4
        if opp_counts["MISSING_UPSELL"] > 0:
            uplift = OPPORTUNITY_UPLIFTS["MISSING_UPSELL"]["uplift_pct"]
            coverage = OPPORTUNITY_UPLIFTS["MISSING_UPSELL"]["coverage"]
            margin = OPPORTUNITY_UPLIFTS["MISSING_UPSELL"]["margin_factor"]
            up = traffic * uplift * aov * margin * coverage
            total_loss += up
            breakdown["MISSING_UPSELL"] = round(up, 2)

        # MISSING_STICKY_ATC: mobile_traffic × 10% uplift × CR × AOV
        if opp_counts["MISSING_STICKY_ATC"] > 0:
            mobile_share = OPPORTUNITY_UPLIFTS["MISSING_STICKY_ATC"]["mobile_share"]
            uplift = OPPORTUNITY_UPLIFTS["MISSING_STICKY_ATC"]["uplift_pct"]
            mobile_traffic = traffic * mobile_share
            sticky = mobile_traffic * uplift * baseline_cr * aov
            total_loss += sticky
            breakdown["MISSING_STICKY_ATC"] = round(sticky, 2)

        est_monthly_loss_usd = round(total_loss, 2)

        # P4: Add breakdown to provenance (auditability)
        for opp_type, value in breakdown.items():
            if value > 0:
                provenance.append(CommercialParameterProvenance(
                    parameter_name=f"loss_from_{opp_type}",
                    value=value,
                    source=ParameterSource.PRIMARY_MEASURED if opp_type == "REVENUE_LEAK" else ParameterSource.FALLBACK_ASSUMED,
                    source_detail=f"{OPPORTUNITY_UPLIFTS[opp_type]['base_formula']} ({opp_counts[opp_type]} occurrences)",
                    confidence_impact=0.0 if opp_type == "REVENUE_LEAK" else -0.02,
                ))

        # Mandatory Fallback Disclosure Lock
        if has_fallback and confidence_score >= 0.70:
            confidence_score = 0.69
        confidence_score = max(0.0, min(1.0, round(confidence_score, 2)))

        # 6. Lead Priority (based on TOTAL loss across all opportunities)
        if est_monthly_loss_usd >= 10000.0:
            lead_priority = "HIGH"
        elif est_monthly_loss_usd >= 2500.0:
            lead_priority = "MEDIUM"
        else:
            lead_priority = "LOW"

        # 7. Footnote Disclosure
        active_opps = [k for k, v in breakdown.items() if v > 0]
        if has_fallback:
            footnote = (
                f"* Revenue loss includes {len(active_opps)} opportunity type(s): {', '.join(active_opps)}. "
                f"Confidence: {confidence_score * 100:.0f}%. Traffic: {traffic:,}/mo; AOV: ${aov:.2f}."
            )
        else:
            footnote = (
                f"* Based on measured OOS ({oos_frequency_pct:.1f}%) and {len(active_opps)} opportunity type(s): "
                f"{', '.join(active_opps)}. Traffic: {traffic:,}/mo."
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
        """Helper returning a validated CommercialImpact DTO directly."""
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
