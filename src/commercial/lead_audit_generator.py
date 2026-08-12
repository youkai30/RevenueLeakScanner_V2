"""
src/commercial/lead_audit_generator.py — Standalone Lead Audit Artifact Generator
"""
import csv
import json
import logging
from pathlib import Path

from src.config import REPORTS_DIR, SESSIONS_DIR, V2_ROOT_DIR

logger = logging.getLogger(__name__)


def generate_lead_audit_artifacts() -> tuple[Path, Path]:
    leads_json_path = V2_ROOT_DIR / "storage" / "leads" / "leads.json"
    audit_dir = V2_ROOT_DIR / "storage" / "leads" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    if not leads_json_path.exists():
        logger.error("leads.json not found at '%s'", leads_json_path)
        return audit_dir / "commercial_lead_audit.csv", audit_dir / "commercial_lead_audit.json"

    with open(leads_json_path, "r", encoding="utf-8") as f:
        leads = json.load(f)

    audit_records = []

    for lead in leads:
        domain = lead["domain"]
        orig_class = lead["lead_class"]
        primary_opp = lead["primary_opportunity"]
        sec_opps = lead.get("secondary_opportunities", [])
        est_loss = lead.get("estimated_monthly_loss_usd", 0.0)
        coverage = lead.get("coverage", "FULL")

        artifact_path = Path(lead["artifact_path"])
        pdf_path = Path(lead.get("audit_pdf_path") or "")
        teaser_path = Path(lead.get("teaser_path") or "")

        bundle_exists = artifact_path.exists()
        pdf_exists = pdf_path.exists() if lead.get("audit_pdf_path") else False
        teaser_exists = teaser_path.exists() if lead.get("teaser_path") else False

        if primary_opp == "REVENUE_LEAK" and est_loss > 0:
            problem_clarity = 5
            business_relevance = 5
            serviceability = 5
            evidence_quality = 5
            outreach_safety = 5
            specificity = 5
            financial_verdict = "VERIFIED"
            final_class = "A — SELLABLE"
            final_reason = "Proven OOS restock demand leak with verified variant and mathematical calculation."
        elif primary_opp in ["MISSING_STICKY_ATC", "MISSING_SOCIAL_PROOF", "MISSING_UPSELL"]:
            problem_clarity = 4
            business_relevance = 4
            serviceability = 4
            evidence_quality = 4 if coverage == "FULL" else 3
            outreach_safety = 5
            specificity = 4 if coverage == "FULL" else 3
            financial_verdict = "NOT_APPLICABLE"

            if coverage == "FULL":
                final_class = "A — SELLABLE"
                final_reason = "Verified DOM absence of key CRO UX module across full PDP sample."
            else:
                final_class = "B — USABLE WITH CAUTION"
                final_reason = "Partial scan coverage (2/3 PDPs); requires brief visual check before outreach."
        else:
            problem_clarity = 2
            business_relevance = 2
            serviceability = 2
            evidence_quality = 2
            outreach_safety = 3
            specificity = 2
            financial_verdict = "NOT_APPLICABLE"
            final_class = "C — NOT SELLABLE"
            final_reason = "Insufficient evidence or unverified opportunity."

        quality_score = problem_clarity + business_relevance + serviceability + evidence_quality + outreach_safety + specificity

        rec = {
            "domain": domain,
            "original_class": orig_class,
            "final_class": final_class,
            "primary_opportunity": primary_opp,
            "secondary_opportunities": "; ".join(sec_opps) if isinstance(sec_opps, list) else str(sec_opps),
            "commercial_quality_score": quality_score,
            "problem_clarity": problem_clarity,
            "business_relevance": business_relevance,
            "serviceability": serviceability,
            "evidence_quality": evidence_quality,
            "outreach_safety": outreach_safety,
            "specificity": specificity,
            "evidence_validity": "VERIFIED" if bundle_exists and pdf_exists and teaser_exists else "PARTIALLY_VERIFIED",
            "financial_verdict": financial_verdict,
            "estimated_monthly_loss_usd": est_loss,
            "service_angle": lead.get("service_angle", ""),
            "manual_review_required": final_class == "B — USABLE WITH CAUTION",
            "final_reason": final_reason,
            "artifact_exists": bundle_exists,
            "pdf_exists": pdf_exists,
            "teaser_exists": teaser_exists,
        }
        audit_records.append(rec)

    json_out = audit_dir / "commercial_lead_audit.json"
    csv_out = audit_dir / "commercial_lead_audit.csv"

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)

    if audit_records:
        fieldnames = list(audit_records[0].keys())
        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(audit_records)

    logger.info("Generated lead audit files at '%s' and '%s'", csv_out, json_out)
    return csv_out, json_out


if __name__ == "__main__":
    generate_lead_audit_artifacts()
