"""
src/presentation/payload_compiler.py — Presentation Payload Compiler Engine

Layer 5: Presentation Payload Builder
"""
from src.config import DEFAULT_AOV_FALLBACK_USD
from src.evidence.models import Finding, SessionBundle
from src.ingestion.tenant_config import TenantConfig
from src.presentation.models import CalloutTag, EmailPayload, FindingPresentation, PDFPayload


class PayloadCompiler:
    """
    Compiles immutable driver-specific DTOs (PDFPayload, EmailPayload) from a verified SessionBundle.
    
    DOES NOT:
      - Scan websites or execute Playwright
      - Calculate or alter financial loss metrics
      - Modify SessionBundle or source PNG files
      - Hardcode agency brand names or client URLs
    """

    def __init__(self, tenant_config: TenantConfig | None = None) -> None:
        self.tenant_config = tenant_config or TenantConfig()

    def _compile_finding_presentation(self, finding: Finding) -> FindingPresentation:
        """Helper transforming a domain Finding DTO into a FindingPresentation DTO."""
        tags: list[CalloutTag] = []
        opps = getattr(finding, "opportunities", [])

        if opps:
            for opp in opps:
                opp_type = opp.get("opportunity_type") if isinstance(opp, dict) else getattr(opp, "opportunity_type", "REVENUE_LEAK")
                prob_summary = opp.get("commercial_problem_summary") if isinstance(opp, dict) else getattr(opp, "commercial_problem_summary", "Conversion leak detected")
                tags.append(
                    CalloutTag(
                        label=f"OPPORTUNITY: {opp_type}",
                        target_element="cta" if "REVENUE" in str(opp_type) or "ATC" in str(opp_type) else "buy_box",
                        color_theme="red" if "REVENUE" in str(opp_type) else "orange",
                    )
                )
        else:
            tags.append(
                CalloutTag(
                    label="STANDARD CRO MAINTENANCE",
                    target_element="buy_box",
                    color_theme="green",
                )
            )

        return FindingPresentation(
            finding_id=str(finding.finding_id),
            product_name=finding.product_name,
            product_url=finding.product_url,
            scanned_variant=finding.scanned_variant,
            out_of_stock=finding.out_of_stock,
            notify_button_detected=finding.notify_button_detected,
            review_widget_detected=finding.review_widget_detected,
            review_platform=finding.review_platform,
            review_count=finding.review_count,
            evidence_image_file=finding.evidence.image_file,
            callout_tags=tags,
        )


    def compile_pdf_payload(self, session_bundle: SessionBundle) -> PDFPayload:
        """Compiles a PDFPayload DTO from a verified SessionBundle."""
        findings_pres = [self._compile_finding_presentation(f) for f in session_bundle.findings]

        # Financial parameters from Phase C commercial object
        comm = session_bundle.commercial

        # Construct mandatory disclosure statement if confidence is penalized
        if comm.confidence_score < 0.70:
            footnote = (
                f"* Note: Revenue loss estimation includes benchmark parameters "
                f"(Confidence Rating: {comm.confidence_score * 100:.0f}%). "
                f"Traffic estimated at {comm.est_monthly_traffic:,} visits/mo; AOV benchmark ${DEFAULT_AOV_FALLBACK_USD:.2f}."
            )
        else:
            footnote = (
                f"* Estimated based on measured PDP out-of-stock sample ratio ({comm.oos_frequency_pct:.1f}%) "
                f"and measured monthly traffic ({comm.est_monthly_traffic:,} visits/mo)."
            )

        return PDFPayload(
            domain=session_bundle.domain,
            session_id=str(session_bundle.session_id),
            build_id=str(session_bundle.build_id),
            timestamp=session_bundle.timestamp,
            schema_version=session_bundle.schema_version,
            est_monthly_loss_usd=comm.est_monthly_loss_usd,
            lead_priority=comm.lead_priority,
            confidence_score=comm.confidence_score,
            est_monthly_traffic=comm.est_monthly_traffic,
            oos_frequency_pct=comm.oos_frequency_pct,
            variants_inspected=comm.variants_inspected,
            variants_oos=comm.variants_oos,
            baseline_cr_pct=2.0,
            aov_usd=DEFAULT_AOV_FALLBACK_USD,
            footnote_disclosure=footnote,
            agency_name=self.tenant_config.agency_name,
            agency_logo_url=self.tenant_config.logo_url,
            primary_color_hex=self.tenant_config.primary_color_hex,
            sdr_booking_link=self.tenant_config.sdr_booking_link,
            findings=findings_pres,
        )

    def compile_email_payload(self, session_bundle: SessionBundle) -> EmailPayload:
        """Compiles an EmailPayload DTO for SDR cold outreach."""
        headline_finding = self._compile_finding_presentation(session_bundle.findings[0])
        teaser_filename = f"teaser_{session_bundle.session_id}.png"

        # Determine opportunity headline wording
        primary_finding = session_bundle.findings[0] if session_bundle.findings else None
        primary_opp_type = "REVENUE_LEAK"
        if primary_finding and getattr(primary_finding, "opportunities", None):
            primary_opp_type = str(primary_finding.opportunities[0].get("opportunity_type", "REVENUE_LEAK"))
        elif primary_finding and primary_finding.out_of_stock and not primary_finding.notify_button_detected:
            primary_opp_type = "REVENUE_LEAK"

        return EmailPayload(
            domain=session_bundle.domain,
            session_id=str(session_bundle.session_id),
            est_monthly_loss_usd=session_bundle.commercial.est_monthly_loss_usd,
            headline_finding=headline_finding,
            teaser_image_file=teaser_filename,
            sdr_booking_link=self.tenant_config.sdr_booking_link,
        )

