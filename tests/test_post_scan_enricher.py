"""
tests/test_post_scan_enricher.py — Unit Tests for Post-Scan Lead Enricher
"""
import pytest
from src.enrichment.post_scan_enricher import PostScanEnricher
from src.evidence.models import SessionBundle, CommercialImpact, Finding, VisualEvidence
from src.scanner.models import CommercialOpportunity, OpportunityType, EvidenceStatus


@pytest.fixture
def sample_session_bundle():
    return SessionBundle(
        domain="toms.co.uk",
        session_id="35fe81ad-c5a7-4954-b3f0-8ea3c6b6f945",
        build_id="a87d270b-9356-4d92-9b31-d3a0def70ace",
        scanner_version="2.3.1",
        checksum="1111111111111111111111111111111111111111111111111111111111111111",
        schema_version="2.0.0",
        timestamp="2026-08-08T17:21:58Z",
        commercial=CommercialImpact(
            est_monthly_loss_usd=1666.67,
            est_monthly_traffic=50000,
            lead_priority="HIGH",
            confidence_score=0.85,
            oos_frequency_pct=2.56,
            variants_inspected=39,
            variants_oos=1,
        ),
        findings=[
            Finding(
                finding_id="11111111-1111-1111-1111-111111111111",
                product_name="Espadrille Suede Shoes - TOMS UK",
                product_url="https://toms.co.uk/products/p1",
                scanned_variant="9",
                out_of_stock=True,
                notify_button_detected=False,
                sold_out_detected=True,
                review_widget_detected=False,
                review_platform="",
                review_count=0,
                upsell_detected=False,
                sticky_atc_detected=True,
                evidence=VisualEvidence(
                    image_file="toms.png",
                    relative_path="https://toms.co.uk/toms.png",
                    sha256_hash="1c9b1846131b4a7680e53763aeb6493e9031b7d1118813d7d930bb593a99e381",
                    width=1024,
                    height=600,
                    viewport="1024x600",
                    capture_duration_ms=400,
                    browser_version="Chrome",
                    valid=True,
                ),
                opportunities=[
                    CommercialOpportunity(
                        opportunity_type=OpportunityType.REVENUE_LEAK,
                        commercial_problem_summary="Out-of-Stock variant '9' has no Back-in-Stock capture modal",
                        sellable_service_angle="Back-In-Stock Restock Capture Flow",
                        is_valid_opportunity=True,
                        evidence_status=EvidenceStatus.VERIFIED,
                    ).model_dump(mode="json")
                ]
            )
        ]
    )


def test_company_name_extraction(sample_session_bundle):
    enricher = PostScanEnricher()
    data = enricher.enrich_bundle(sample_session_bundle)
    assert data["company_name"] == "Toms"
    assert data["company_name_source"] == "DOMAIN_NAME"
    assert data["company_name"] != "Espadrille Suede Shoes"


def test_country_detection_tld(sample_session_bundle):
    enricher = PostScanEnricher()
    data = enricher.enrich_bundle(sample_session_bundle)
    assert data["country_name"] == "United Kingdom"
    assert data["country_code"] == "GB"
    assert data["country_source"] == "TLD"
    assert data["country_confidence"] == "HIGH"


def test_generic_com_country_unknown(sample_session_bundle):
    bundle = sample_session_bundle.model_copy(update={"domain": "toms.com"})
    enricher = PostScanEnricher()
    data = enricher.enrich_bundle(bundle)
    assert data["country_name"] is None
    assert data["country_code"] is None
    assert data["country_source"] == "UNKNOWN"
    assert data["country_confidence"] == "NONE"


def test_social_url_sanitization():
    enricher = PostScanEnricher()

    # Valid Instagram handle with query parameter
    clean = enricher.sanitize_social_url("instagram.com", "https://instagram.com/toms?utm_source=footer")
    assert clean == "https://instagram.com/toms"

    # Homepage rejection
    homepage = enricher.sanitize_social_url("instagram.com", "https://instagram.com")
    assert homepage is None

    # Share link rejection
    share_link = enricher.sanitize_social_url("facebook.com", "https://facebook.com/sharer/sharer.php?u=foo")
    assert share_link is None


def test_contact_page_inferencing(sample_session_bundle):
    enricher = PostScanEnricher()
    data = enricher.enrich_bundle(sample_session_bundle)
    assert data["contact_page"] == "https://toms.co.uk/pages/contact"
    # DEF-02 Fix: inferred /pages/contact must be INFERRED_DOMAIN_PATH, never DOM_LINK
    assert data["contact_page_source"] == "INFERRED_DOMAIN_PATH"
    assert data["contact_page_source"] != "DOM_LINK"


def test_enrichment_failure_isolation(sample_session_bundle):
    enricher = PostScanEnricher()
    # Force invalid bundle property to test graceful failure
    data = enricher.enrich_bundle(None)
    assert data["enrichment_status"] == "FAILED"
    assert len(data["enrichment_errors"]) > 0
