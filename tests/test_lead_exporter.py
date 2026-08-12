"""
tests/test_lead_exporter.py — Unit Tests for Commercial Lead Exporter Pipeline
"""
import pytest
from pathlib import Path
from src.commercial.lead_exporter import CommercialLeadExporter, CommercialLeadRecord
from src.evidence.models import SessionBundle, CommercialImpact, Finding, VisualEvidence
from src.scanner.models import CommercialOpportunity, OpportunityType, EvidenceStatus


@pytest.fixture
def sample_session_bundle():
    from src.config import SESSIONS_DIR
    session_id = "35fe81ad-c5a7-4954-b3f0-8ea3c6b6f945"
    path = SESSIONS_DIR / "toms.com" / session_id / "toms.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fp:
        fp.write(b"MOCK_PNG")

    return SessionBundle(
        domain="toms.com",
        session_id=session_id,
        build_id="a87d270b-9356-4d92-9b31-d3a0def70ace",
        scanner_version="2.3.1",
        checksum="1111111111111111111111111111111111111111111111111111111111111111",
        schema_version="2.0.0",
        timestamp="2026-08-08T17:21:58Z",
        contact_info={"instagram_url": "https://instagram.com/toms"},
        commercial=CommercialImpact(
            est_monthly_loss_usd=1666.67,
            est_monthly_traffic=50000,
            lead_priority="HIGH",
            confidence_score=0.85,
            oos_frequency_pct=2.56,
            variants_inspected=39,
            variants_oos=1,
            financial_loss_status="ESTIMATED",
        ),

        findings=[
            Finding(
                finding_id="11111111-1111-1111-1111-111111111111",
                product_name="Espadrille Suede",
                product_url="https://toms.com/p1",
                scanned_variant="9",
                out_of_stock=True,
                notify_button_detected=False,
                sold_out_detected=True,
                review_widget_detected=False,
                review_platform="",
                review_count=0,
                upsell_detected=False,
                sticky_atc_detected=True,
                bis_detection_state="FALSE",
                review_detection_state="FALSE",
                upsell_detection_state="FALSE",
                sticky_atc_detection_state="TRUE",
                evidence=VisualEvidence(
                    image_file="toms.png",
                    relative_path="https://toms.com/toms.png",
                    sha256_hash="1c9b1846131b4a7680e53763aeb6493e9031b7d1118813d7d930bb593a99e381",
                    width=1024,
                    height=600,
                    viewport="1024x600",
                    capture_duration_ms=400,
                    browser_version="Chrome",
                    valid=True,
                    finding_id="11111111-1111-1111-1111-111111111111",
                    pdp_url="https://toms.com/p1",
                    store_domain="toms.com",
                    evidence_id="22222222-2222-2222-2222-222222222222",
                ),
                opportunities=[
                    CommercialOpportunity(
                        opportunity_type=OpportunityType.REVENUE_LEAK,
                        commercial_problem_summary="Out-of-Stock variant '9' has no Back-in-Stock capture modal",
                        sellable_service_angle="Back-In-Stock Restock Capture Flow",
                        is_valid_opportunity=True,
                        evidence_status=EvidenceStatus.VERIFIED,
                    ).model_dump(mode="json"),
                    CommercialOpportunity(
                        opportunity_type=OpportunityType.MISSING_SOCIAL_PROOF,
                        commercial_problem_summary="Buy Box fold lacks rating badges",
                        sellable_service_angle="Social Proof Setup",
                        is_valid_opportunity=True,
                        evidence_status=EvidenceStatus.VERIFIED,
                    ).model_dump(mode="json"),
                ]
            )
        ]

    )


def test_one_store_one_lead_deduplication(sample_session_bundle):
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(sample_session_bundle, scan_duration_seconds=27.81)

    assert isinstance(lead, CommercialLeadRecord)
    assert lead.domain == "toms.com"
    assert lead.primary_opportunity == "REVENUE_LEAK"
    assert "MISSING_SOCIAL_PROOF" in lead.secondary_opportunities
    assert lead.estimated_monthly_loss_usd == 1666.67
    assert lead.lead_class == "A — SELLABLE"
    assert lead.commercial_priority == "HIGH"
    assert lead.lead_type_category == "CONFIRMED_REVENUE_LEAK"


def test_zero_loss_non_downgrade(sample_session_bundle):
    # Modify bundle to have $0 loss and CRO opportunity
    zero_loss_commercial = CommercialImpact(
        est_monthly_loss_usd=0.0,
        est_monthly_traffic=50000,
        lead_priority="LOW",
        confidence_score=0.65,
        oos_frequency_pct=0.0,
        variants_inspected=3,
        variants_oos=0,
        financial_loss_status="ESTIMATED",
    )

    bundle = sample_session_bundle.model_copy(update={
        "commercial": zero_loss_commercial,
        "findings": [sample_session_bundle.findings[0]] * 3,
        "contact_info": {"instagram_url": "https://instagram.com/toms"}
    })
    bundle.findings[0].opportunities.pop(0)  # Remove REVENUE_LEAK


    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(bundle, scan_duration_seconds=12.0)

    assert lead.domain == "toms.com"
    assert lead.primary_opportunity == "MISSING_SOCIAL_PROOF"
    assert lead.estimated_monthly_loss_usd == 0.0
    assert lead.loss_basis == "NO_CONFIRMED_OOS_LEAK"
    assert lead.lead_class == "A — SELLABLE"  # CRO leads are still Class A!


def test_export_leads_csv_and_json(tmp_path, sample_session_bundle):
    exporter = CommercialLeadExporter()
    lead = exporter.assemble_lead(sample_session_bundle, scan_duration_seconds=27.81)

    csv_path, json_path = exporter.export_leads([lead], output_dir=tmp_path)

    assert csv_path.exists()
    assert json_path.exists()

    content = json_path.read_text(encoding="utf-8")
    assert "toms.com" in content
    assert "CONFIRMED_REVENUE_LEAK" in content
