"""
src/commercial/lead_exporter.py — Commercial Lead Assembly & Export Pipeline

Layer 3: Commercial Intelligence Lead Exporter
"""
import csv
import json
import logging
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from src.config import REPORTS_DIR, SESSIONS_DIR
from src.evidence.models import SessionBundle
from src.evidence.session_storage import SessionStorage

logger = logging.getLogger(__name__)


class CommercialLeadRecord(BaseModel):
    """
    Production-ready commercial lead record DTO.
    Deduplicated at 1 store = 1 lead level.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(description="Target store domain")
    lead_class: str = Field(description="Commercial classification: 'A — SELLABLE', 'B — USABLE WITH CAUTION', 'C — NOT SELLABLE'")
    commercial_priority: str = Field(description="Priority tier: 'HIGH', 'MEDIUM', 'LOW'")
    lead_type_category: str = Field(description="Categorization: 'CONFIRMED_REVENUE_LEAK', 'STRONG_CRO_OPPORTUNITY', 'REVIEW_REQUIRED'")
    primary_opportunity: str = Field(description="Highest priority opportunity type")
    secondary_opportunities: list[str] = Field(default_factory=list, description="List of secondary opportunity types")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall scan confidence rating")
    evidence_validity: str = Field(description="Overall visual evidence status")
    estimated_monthly_loss_usd: float = Field(default=0.0, ge=0.0, description="Calculated lost revenue USD")
    loss_basis: str = Field(description="Financial loss calculation basis")
    affected_product: str | None = Field(default=None, description="Primary affected product name")
    affected_variant: str | None = Field(default=None, description="Primary affected variant name")
    exact_problem: str = Field(description="Exact commercial problem statement")
    service_angle: str = Field(description="Recommended agency sellable service angle")
    outreach_safe: bool = Field(default=True, description="Whether lead is safe for direct cold outreach")
    manual_review_required: bool = Field(default=False, description="Whether manual visual review is required")
    coverage: str = Field(default="FULL", description="Scan coverage: FULL or PARTIAL")
    pdps_inspected: int = Field(default=3, description="Number of PDPs inspected")
    scan_duration_seconds: float = Field(default=0.0, description="Store scan wall-clock duration in seconds")
    session_id: str = Field(description="Session UUID string")
    artifact_path: str = Field(description="Path to SessionBundle JSON")
    audit_pdf_path: str | None = Field(default=None, description="Path to Executive Audit PDF")
    teaser_path: str | None = Field(default=None, description="Path to Outreach Teaser PNG")
    screenshot_evidence_path: str | None = Field(default=None, description="Path to primary evidence screenshot PNG")
    generated_at: str = Field(description="Timestamp UTC ISO string")

    # Additive Enrichment Metadata Fields (P0, P1, P2 + Provenance)
    company_name: str | None = Field(default=None, description="Extracted clean company/brand name")
    company_name_source: str = Field(default="NOT_FOUND", description="'JSON_LD', 'OG_SITE_NAME', 'APPLICATION_NAME', 'TITLE', 'NOT_FOUND'")
    contact_email: str | None = Field(default=None, description="Scraped support/sales contact email address")
    contact_email_source: str = Field(default="NOT_FOUND", description="'MAILTO', 'FOOTER_TEXT', 'CONTACT_PAGE_TEXT', 'NOT_FOUND'")
    contact_page: str | None = Field(default=None, description="Absolute URL to target store Contact page")
    contact_page_source: str = Field(default="NOT_FOUND", description="'DOM_LINK', 'NOT_FOUND'")
    contact_phone: str | None = Field(default=None, description="Extracted customer support phone number")
    contact_phone_source: str = Field(default="NOT_FOUND", description="'TEL_LINK', 'FOOTER_TEXT', 'NOT_FOUND'")

    country_name: str | None = Field(default=None, description="Detected target store country name")
    country_code: str | None = Field(default=None, description="ISO 2-letter country code")
    country_source: str = Field(default="UNKNOWN", description="'TLD', 'HTML_LANG', 'OG_LOCALE', 'UNKNOWN'")
    country_confidence: str = Field(default="NONE", description="'HIGH', 'MEDIUM', 'NONE'")

    instagram_url: str | None = Field(default=None, description="Clean Instagram profile URL")
    facebook_url: str | None = Field(default=None, description="Clean Facebook page URL")
    linkedin_url: str | None = Field(default=None, description="Clean LinkedIn company page URL")
    tiktok_url: str | None = Field(default=None, description="Clean TikTok profile URL")
    youtube_url: str | None = Field(default=None, description="Clean YouTube channel URL")
    x_url: str | None = Field(default=None, description="Clean X / Twitter profile URL")

    enrichment_attempted: bool = Field(default=False, description="True if post-scan enrichment was executed")
    enrichment_status: str = Field(default="NOT_ATTEMPTED", description="'SUCCESS', 'PARTIAL', 'FAILED', 'NOT_ATTEMPTED'")
    enrichment_timestamp: str | None = Field(default=None, description="UTC ISO timestamp of enrichment execution")
    enrichment_errors: list[str] = Field(default_factory=list, description="Non-fatal enrichment diagnostic error messages")


class CommercialLeadExporter:
    """
    Assembles, deduplicates, ranks, and exports CommercialLeadRecord objects from SessionBundle artifacts.
    """

    OPPORTUNITY_PRIORITY = {
        "REVENUE_LEAK": 1,
        "MISSING_STICKY_ATC": 2,
        "MISSING_SOCIAL_PROOF": 3,
        "MISSING_UPSELL": 4,
    }

    def assemble_lead(
        self,
        bundle: SessionBundle,
        scan_duration_seconds: float = 0.0,
    ) -> CommercialLeadRecord:
        """
        Transforms a SessionBundle into a single deduplicated CommercialLeadRecord.
        """
        all_opps: list[dict[str, Any]] = []
        affected_product = None
        affected_variant = None
        primary_finding_evidence_path = None

        # 1. Collect all opportunities across PDP findings
        for f in bundle.findings:
            if hasattr(f, "evidence") and f.evidence and getattr(f.evidence, "valid", False):
                if not primary_finding_evidence_path:
                    primary_finding_evidence_path = f.evidence.relative_path

            if hasattr(f, "opportunities") and f.opportunities:
                for opp in f.opportunities:
                    opp_dict = opp if isinstance(opp, dict) else opp.model_dump(mode="json")
                    all_opps.append(opp_dict)
                    if opp_dict.get("opportunity_type") == "REVENUE_LEAK" and f.product_name:
                        affected_product = f.product_name
                        affected_variant = f.scanned_variant

        if not affected_product and bundle.findings:
            affected_product = bundle.findings[0].product_name
            affected_variant = bundle.findings[0].scanned_variant

        # Deduplicate opportunity types
        unique_opp_types: set[str] = set()
        opp_by_type: dict[str, dict[str, Any]] = {}
        for opp in all_opps:
            opp_type = opp.get("opportunity_type", "")
            if opp_type:
                unique_opp_types.add(opp_type)
                if opp_type not in opp_by_type:
                    opp_by_type[opp_type] = opp

        # 2. Determine Primary vs Secondary Opportunities
        sorted_types = sorted(
            list(unique_opp_types),
            key=lambda t: self.OPPORTUNITY_PRIORITY.get(t, 99)
        )

        is_blocked = any(
            str(getattr(f.page_state, "value", f.page_state) if getattr(f, "page_state", None) else "").upper() in ("CLOUDFLARE_BLOCKED", "ERROR", "PARTIALLY_INSPECTED", "UNKNOWN")
            for f in bundle.findings
        )

        if sorted_types:
            primary_opp_type = sorted_types[0]
            secondary_opp_types = sorted_types[1:]
        elif is_blocked:
            primary_opp_type = "SCAN_BLOCKED"
            secondary_opp_types = []
        else:
            primary_opp_type = "NONE_DETECTED"
            secondary_opp_types = []

        primary_opp_data = opp_by_type.get(primary_opp_type, {})
        default_problem = "Scan blocked by Cloudflare / Anti-Bot protection" if is_blocked else "No confirmed revenue leaks detected"
        exact_problem = primary_opp_data.get("commercial_problem_summary", default_problem)
        service_angle = primary_opp_data.get(
            "sellable_service_angle", "Full E-Commerce CRO & Audit Service"
        )

        # 3. Financial Loss & Basis
        est_loss = bundle.commercial.est_monthly_loss_usd or 0.0
        if est_loss > 0.0 and primary_opp_type == "REVENUE_LEAK":
            loss_basis = f"Measured OOS Ratio ({bundle.commercial.oos_frequency_pct:.1f}%) * AOV * Baseline CR * Traffic"
            lead_category = "CONFIRMED_REVENUE_LEAK"
        elif is_blocked or primary_opp_type == "SCAN_BLOCKED":
            loss_basis = "NO_CONFIRMED_OOS_LEAK"
            lead_category = "BLOCKED_OR_UNVERIFIED"
        else:
            loss_basis = "NO_CONFIRMED_OOS_LEAK"
            lead_category = "STRONG_CRO_OPPORTUNITY"

        # 4. Coverage & Lead Classification (DEF-05 Fix: Require brand & contactability for Class A)
        pdps_count = len(bundle.findings)
        coverage_status = "FULL" if pdps_count >= 3 else "PARTIAL"

        # Run enrichment before classification so brand/contact gates are available
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        enrichment_data = enricher.enrich_bundle(bundle)

        has_brand = bool(enrichment_data.get("company_name")) and enrichment_data.get("company_name_source") != "NOT_FOUND"
        has_contact_channel = bool(
            enrichment_data.get("contact_email")
            or enrichment_data.get("contact_phone")
            or (enrichment_data.get("contact_page") and enrichment_data.get("contact_page_source") != "INFERRED_DOMAIN_PATH")
            or enrichment_data.get("instagram_url")
            or enrichment_data.get("facebook_url")
            or enrichment_data.get("linkedin_url")
            or enrichment_data.get("tiktok_url")
            or enrichment_data.get("youtube_url")
            or enrichment_data.get("x_url")
        )

        # Safety invariants checks (DEF-04)
        has_cloudflare_block = any(
            str(getattr(f.page_state, "value", f.page_state) if getattr(f, "page_state", None) else "").upper() == "CLOUDFLARE_BLOCKED"
            for f in bundle.findings
        )
        has_invalid_or_unknown_pdp = any(
            str(getattr(f.page_state, "value", f.page_state) if getattr(f, "page_state", None) else "").upper() in ("CLOUDFLARE_BLOCKED", "ERROR", "UNKNOWN")
            for f in bundle.findings
        )
        has_partial_inspection = any(
            str(getattr(f.page_state, "value", f.page_state) if getattr(f, "page_state", None) else "").upper() == "PARTIALLY_INSPECTED"
            for f in bundle.findings
        )

        has_unknown_detector = any(
            str(getattr(f, "bis_detection_state", "UNKNOWN")).upper() == "UNKNOWN"
            or str(getattr(f, "review_detection_state", "UNKNOWN")).upper() == "UNKNOWN"
            or str(getattr(f, "upsell_detection_state", "UNKNOWN")).upper() == "UNKNOWN"
            or str(getattr(f, "sticky_atc_detection_state", "UNKNOWN")).upper() == "UNKNOWN"
            for f in bundle.findings
        )

        has_invalid_evidence_binding = any(
            not getattr(f, "evidence", None)
            or not getattr(f.evidence, "valid", False)
            or str(getattr(f.evidence, "finding_id", "")) != str(f.finding_id)
            or getattr(f.evidence, "pdp_url", "") != f.product_url
            or not (SESSIONS_DIR / bundle.domain / str(bundle.session_id) / f.evidence.image_file).exists()
            for f in bundle.findings
        )

        financial_status = getattr(bundle.commercial, "financial_loss_status", "UNKNOWN")

        is_class_a_eligible = (
            not has_invalid_or_unknown_pdp
            and not has_partial_inspection
            and not has_unknown_detector
            and not has_invalid_evidence_binding
            and has_brand
            and has_contact_channel
            and financial_status != "UNKNOWN"
        )

        if primary_opp_type == "REVENUE_LEAK" and est_loss > 0.0 and is_class_a_eligible:
            lead_class = "A — SELLABLE"
            comm_priority = "HIGH"
            outreach_safe = True
            manual_review = False
        elif len(unique_opp_types) >= 1 and coverage_status == "FULL" and is_class_a_eligible:
            lead_class = "A — SELLABLE"
            comm_priority = "MEDIUM" if est_loss == 0.0 else "HIGH"
            outreach_safe = True
            manual_review = False
        elif has_cloudflare_block:
            lead_class = "C — NOT SELLABLE"
            comm_priority = "LOW"
            outreach_safe = False
            manual_review = True
        elif len(unique_opp_types) >= 1:
            lead_class = "B — USABLE WITH CAUTION"
            comm_priority = "LOW"
            outreach_safe = True
            manual_review = True
        else:
            lead_class = "C — NOT SELLABLE"
            comm_priority = "LOW"
            outreach_safe = False
            manual_review = True

        # 5. Artifact Paths Resolution
        reports_dir = REPORTS_DIR / bundle.domain / str(bundle.session_id)
        session_dir = SESSIONS_DIR / bundle.domain / str(bundle.session_id)

        artifact_json = session_dir / f"session_{bundle.session_id}.json"
        pdf_path = reports_dir / "audit.pdf"
        teaser_path = reports_dir / "teaser.png"

        # (Enrichment was already run during classification — no second call needed)

        return CommercialLeadRecord(
            domain=bundle.domain,
            lead_class=lead_class,
            commercial_priority=comm_priority,
            lead_type_category=lead_category,
            primary_opportunity=primary_opp_type,
            secondary_opportunities=secondary_opp_types,
            confidence=bundle.commercial.confidence_score,
            evidence_validity=(
                "VERIFIED"
                if (
                    len(bundle.findings) > 0
                    and all(
                        getattr(f.evidence, "valid", False)
                        and (SESSIONS_DIR / bundle.domain / str(bundle.session_id) / f.evidence.image_file).exists()
                        for f in bundle.findings
                        if getattr(f, "evidence", None)
                    )
                )
                else "NONE_DETECTED"
                if len(bundle.findings) == 0
                else "PARTIALLY_VERIFIED"
            ),
            estimated_monthly_loss_usd=est_loss,
            loss_basis=loss_basis,
            affected_product=affected_product,
            affected_variant=affected_variant,
            exact_problem=exact_problem,
            service_angle=service_angle,
            outreach_safe=outreach_safe,
            manual_review_required=manual_review,
            coverage=coverage_status,
            pdps_inspected=pdps_count,
            scan_duration_seconds=round(scan_duration_seconds, 2),
            session_id=str(bundle.session_id),
            artifact_path=str(artifact_json),
            audit_pdf_path=str(pdf_path) if pdf_path.exists() else None,
            teaser_path=str(teaser_path) if teaser_path.exists() else None,
            screenshot_evidence_path=primary_finding_evidence_path,
            generated_at=bundle.timestamp,
            **enrichment_data,
        )

    def export_leads(
        self,
        leads: list[CommercialLeadRecord],
        output_dir: Path,
    ) -> tuple[Path, Path]:
        """
        Exports list of CommercialLeadRecord objects to leads.csv and leads.json.
        Returns tuple of (csv_path, json_path).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "leads.csv"
        json_path = output_dir / "leads.json"

        # Export JSON
        leads_data = [lead.model_dump(mode="json") for lead in leads]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(leads_data, f, indent=2)

        # Export CSV
        if leads:
            fieldnames = list(leads[0].model_dump(mode="json").keys())
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for lead in leads:
                    row = lead.model_dump(mode="json")
                    if isinstance(row.get("secondary_opportunities"), list):
                        row["secondary_opportunities"] = "; ".join(row["secondary_opportunities"])
                    if isinstance(row.get("enrichment_errors"), list):
                        row["enrichment_errors"] = "; ".join(row["enrichment_errors"])
                    writer.writerow(row)

        logger.info("Exported %d commercial leads to '%s' and '%s'", len(leads), csv_path, json_path)
        return csv_path, json_path

    def export_current_run_leads(
        self,
        execution_results: list[Any],
        output_dir: Path | None = None,
    ) -> tuple[Path, Path]:
        """
        Loads SessionBundles strictly for the current run's successful store execution results,
        assembles CommercialLeadRecord objects, and exports them to leads.json and leads.csv.
        Prevents legacy sessions from contaminating the current run export dataset.
        """
        from src.config import V2_ROOT_DIR
        out_dir = output_dir or (V2_ROOT_DIR / "storage" / "leads")
        current_leads: list[CommercialLeadRecord] = []

        for res in execution_results:
            res_dict = res.model_dump(mode="json") if hasattr(res, "model_dump") else res
            status = res_dict.get("status")
            json_path_str = res_dict.get("session_json_path")

            if status == "SUCCESS" and json_path_str:
                json_path = Path(json_path_str)
                if json_path.exists():
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            bundle_data = json.load(f)
                        bundle = SessionBundle.model_validate(bundle_data)
                        duration_sec = (res_dict.get("duration_ms") or 0) / 1000.0
                        lead = self.assemble_lead(bundle, scan_duration_seconds=duration_sec)
                        current_leads.append(lead)
                    except Exception as exc:
                        logger.error("Failed compiling lead from session '%s': %s", json_path, exc)
                        raise RuntimeError(f"Commercial lead compilation failed for session '{json_path}': {exc}") from exc

        return self.export_leads(current_leads, output_dir=out_dir)
