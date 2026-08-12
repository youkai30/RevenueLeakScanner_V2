"""
src/selection/evidence_scorer.py — Evidence Candidate Ranking Scorer

Layer 4: Evidence Scoring & Ranking Engine
"""
import logging
from src.evidence.models import SessionBundle

logger = logging.getLogger(__name__)


class EvidenceScorer:
    """
    Computes a deterministic evidence rank score [0.0, 100.0] for SessionBundle objects.
    Prioritizes high revenue loss magnitude ($/mo), OOS variant count, verified visual evidence,
    and high confidence scores.
    """

    def calculate_score(self, bundle: SessionBundle) -> float:
        """
        Computes evidence quality score [0.0, 100.0] based on weighted heuristics:
          - Lost Revenue magnitude ($/mo): up to 40 pts
          - Out-of-Stock count & ratio: up to 25 pts
          - Confidence rating: up to 20 pts
          - Review & CRO stack signals: up to 15 pts
        """
        score = 0.0

        # 1. Lost Revenue Score (max 40 pts)
        loss = bundle.commercial.est_monthly_loss_usd
        if loss >= 10000.0:
            score += 40.0
        elif loss >= 5000.0:
            score += 30.0
        elif loss >= 2500.0:
            score += 20.0
        else:
            score += min(15.0, (loss / 2500.0) * 15.0)

        # 2. OOS Variant Density (max 25 pts)
        oos_pct = bundle.commercial.oos_frequency_pct
        score += min(25.0, (oos_pct / 20.0) * 25.0)

        # 3. Confidence Score (max 20 pts)
        conf = bundle.commercial.confidence_score
        score += (conf * 20.0)

        # 4. Validated Commercial Opportunity Score (F-03 Fix: Count Unique Store-Level Opportunities)
        unique_store_opp_types: set[str] = set()
        for f in bundle.findings:
            if hasattr(f, "opportunities") and f.opportunities:
                for opp in f.opportunities:
                    opp_type = opp.get("opportunity_type") if isinstance(opp, dict) else getattr(opp, "opportunity_type", None)
                    if opp_type:
                        opp_type_str = opp_type.value if hasattr(opp_type, "value") else str(opp_type)
                        unique_store_opp_types.add(opp_type_str)
            elif f.out_of_stock and not f.notify_button_detected and bool(getattr(f, "scanned_variant_id", "")):
                unique_store_opp_types.add("REVENUE_LEAK")

        score += min(15.0, len(unique_store_opp_types) * 5.0)

        return max(0.0, min(100.0, round(score, 2)))



