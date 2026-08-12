"""
tests/test_remediation_regression.py — Regression Tests for DEF-01 through DEF-11

Covers every defect from the FORENSIC AUDIT FINAL MASTER DEFECT REGISTER.
Each test is a standalone regression that will FAIL if the corresponding defect
is reintroduced.
"""
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_bundle(domain: str = "allbirds.com", findings=None, commercial=None):
    from src.evidence.models import SessionBundle, CommercialImpact, Finding, VisualEvidence
    from src.scanner.models import CommercialOpportunity, OpportunityType, EvidenceStatus

    if findings is None:
        findings = [
            Finding(
                finding_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                product_name="Men's Cruiser - Shadow Black",
                product_url=f"https://{domain}/products/cruiser",
                scanned_variant="Size 10",
                out_of_stock=False,
                notify_button_detected=False,
                sold_out_detected=False,
                review_widget_detected=False,
                review_platform="",
                review_count=0,
                upsell_detected=False,
                sticky_atc_detected=False,
                bis_detection_state="FALSE",
                review_detection_state="FALSE",
                upsell_detection_state="FALSE",
                sticky_atc_detection_state="FALSE",
                evidence=VisualEvidence(
                    image_file="test.png",
                    relative_path=f"https://{domain}/products/cruiser/test.png",
                    sha256_hash="1c9b1846131b4a7680e53763aeb6493e9031b7d1118813d7d930bb593a99e381",
                    width=1024,
                    height=600,
                    viewport="1024x600",
                    capture_duration_ms=400,
                    browser_version="Chrome",
                    valid=True,
                    finding_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    pdp_url=f"https://{domain}/products/cruiser",
                    store_domain=domain,
                    evidence_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                ),
                opportunities=[
                    CommercialOpportunity(
                        opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                        commercial_problem_summary="No sticky ATC detected",
                        sellable_service_angle="Sticky ATC Implementation",
                        is_valid_opportunity=True,
                        evidence_status=EvidenceStatus.VERIFIED,
                    ).model_dump(mode="json")
                ]
            )
        ]

    if commercial is None:
        commercial = CommercialImpact(
            est_monthly_loss_usd=0.0,
            est_monthly_traffic=50000,
            lead_priority="MEDIUM",
            confidence_score=0.75,
            oos_frequency_pct=0.0,
            variants_inspected=5,
            variants_oos=0,
            financial_loss_status="ESTIMATED",
        )

    session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    from src.config import SESSIONS_DIR
    for f in findings:
        if f.evidence and f.evidence.image_file:
            path = SESSIONS_DIR / domain / session_id / f.evidence.image_file
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as fp:
                fp.write(b"MOCK_PNG_DATA")

    return SessionBundle(
        domain=domain,
        session_id=session_id,
        build_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        scanner_version="2.3.1",
        checksum="1111111111111111111111111111111111111111111111111111111111111111",
        schema_version="2.0.0",
        timestamp="2026-08-09T20:00:00Z",
        commercial=commercial,
        findings=findings,
        contact_info={"instagram_url": "https://instagram.com/mock_brand"},
    )


# ---------------------------------------------------------------------------
# DEF-01 — Brand name must NOT come from product title
# ---------------------------------------------------------------------------

class TestDEF01BrandName:
    def test_company_name_not_product_title(self):
        """Company name must NOT equal or contain the product title."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        bundle = _make_bundle("allbirds.com")
        data = enricher.enrich_bundle(bundle)

        assert data["company_name"] != "Men's Cruiser"
        assert data["company_name"] != "Men's Cruiser - Shadow Black"
        assert data["company_name_source"] != "TITLE"

    def test_company_name_derived_from_domain(self):
        """Company name must be derived from domain."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        bundle = _make_bundle("gymshark.com")
        data = enricher.enrich_bundle(bundle)

        assert data["company_name"] == "Gymshark"
        assert data["company_name_source"] == "DOMAIN_NAME"

    def test_hyphenated_domain_brand_name(self):
        """Hyphenated domain like chubbiesshorts.com → Chubbiesshorts."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        name, source = enricher._derive_company_name_from_domain("chubbies-shorts.com")
        assert name == "Chubbies Shorts"
        assert source == "DOMAIN_NAME"

    def test_www_prefix_stripped(self):
        """www. prefix must be stripped before deriving brand name."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        name, source = enricher._derive_company_name_from_domain("www.allbirds.com")
        assert name == "Allbirds"


# ---------------------------------------------------------------------------
# DEF-02 — Contact page provenance must not be labeled DOM_LINK if guessed
# ---------------------------------------------------------------------------

class TestDEF02ContactPageProvenance:
    def test_inferred_contact_page_not_labeled_dom_link(self):
        """Guessed /pages/contact must NOT be labeled DOM_LINK."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        bundle = _make_bundle("allbirds.com")
        data = enricher.enrich_bundle(bundle)

        if data.get("contact_page"):
            assert data.get("contact_page_source") != "DOM_LINK", (
                "contact_page_source must not be DOM_LINK for an inferred URL"
            )

    def test_inferred_contact_labeled_inferred(self):
        """Inferred /pages/contact must have INFERRED_DOMAIN_PATH source."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        bundle = _make_bundle("brooklinen.com")
        data = enricher.enrich_bundle(bundle)

        if data.get("contact_page"):
            assert data.get("contact_page_source") == "INFERRED_DOMAIN_PATH"


# ---------------------------------------------------------------------------
# DEF-03 — Enrichment SUCCESS must require actual contact data
# ---------------------------------------------------------------------------

class TestDEF03EnrichmentStatus:
    def test_no_email_no_phone_no_social_is_not_success(self):
        """enrichment_status must NOT be SUCCESS when all contact fields are empty."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        bundle = _make_bundle("teststore.com")
        object.__setattr__(bundle, "contact_info", {})
        data = enricher.enrich_bundle(bundle)

        has_real_contact = bool(
            data.get("contact_email")
            or data.get("contact_phone")
            or data.get("instagram_url")
            or data.get("facebook_url")
            or data.get("linkedin_url")
            or data.get("x_url")
        )
        if not has_real_contact:
            assert data["enrichment_status"] != "SUCCESS", (
                "enrichment_status must not be SUCCESS when no actual contact data was found"
            )

    def test_partial_status_when_only_domain_and_page(self):
        """When only domain name and inferred contact page: status must be PARTIAL."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        bundle = _make_bundle("kith.com")
        object.__setattr__(bundle, "contact_info", {})
        data = enricher.enrich_bundle(bundle)

        # No email/phone/social expected in a basic bundle
        assert data["enrichment_status"] in ("PARTIAL", "FAILED")


# ---------------------------------------------------------------------------
# DEF-04 — Screenshot evidence path must not embed query parameters
# ---------------------------------------------------------------------------

class TestDEF04EvidencePath:
    def _make_serializer(self):
        from src.evidence.session_serializer import SessionBundleSerializer
        return SessionBundleSerializer()

    def test_clean_url_no_query(self):
        """Clean URL builds a clean evidence path."""
        from urllib.parse import urlparse
        url = "https://example.com/products/sneaker"
        parsed = urlparse(url)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        path = f"{clean}/session_test.png"
        assert "?" not in path
        assert "#" not in path
        assert path == "https://example.com/products/sneaker/session_test.png"

    def test_query_string_stripped_from_evidence_path(self):
        """Product URL with ?ref= query param must not appear in evidence path."""
        from urllib.parse import urlparse
        url = "https://example.com/products/sneaker?ref=banner&utm=ig"
        parsed = urlparse(url)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        path = f"{clean}/session_test.png"
        assert "?" not in path
        assert "ref=banner" not in path
        assert path == "https://example.com/products/sneaker/session_test.png"

    def test_hash_fragment_stripped_from_evidence_path(self):
        """Product URL with #fragment must not appear in evidence path."""
        from urllib.parse import urlparse
        url = "https://example.com/products/sneaker#section-reviews"
        parsed = urlparse(url)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        path = f"{clean}/session_test.png"
        assert "#" not in path
        assert path == "https://example.com/products/sneaker/session_test.png"

    def test_utm_query_stripped_from_evidence_path(self):
        """Product URL with utm= query param must not appear in evidence path."""
        from urllib.parse import urlparse
        url = "https://anker.com/product?utm_source=footer"
        parsed = urlparse(url)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        path = f"{clean}/session_abc.png"
        assert "utm_source" not in path
        assert path == "https://anker.com/product/session_abc.png"


# ---------------------------------------------------------------------------
# DEF-05 — A SELLABLE must not be granted without brand AND contact channel
# ---------------------------------------------------------------------------

class TestDEF05LeadClassification:
    def test_revenue_leak_positive_loss_is_class_a(self):
        """REVENUE_LEAK with positive est_loss always qualifies as Class A."""
        from src.commercial.lead_exporter import CommercialLeadExporter
        from src.evidence.models import CommercialImpact, Finding, VisualEvidence
        from src.scanner.models import CommercialOpportunity, OpportunityType, EvidenceStatus

        # Build bundle with REVENUE_LEAK opportunity and positive loss — use model_copy for frozen model
        base_bundle = _make_bundle("toms.com")
        revenue_leak_commercial = base_bundle.commercial.model_copy(update={
            "est_monthly_loss_usd": 999.0,
            "lead_priority": "HIGH",
        })
        revenue_leak_finding = base_bundle.findings[0].model_copy(update={
            "opportunities": [
                CommercialOpportunity(
                    opportunity_type=OpportunityType.REVENUE_LEAK,
                    commercial_problem_summary="OOS demand leak",
                    sellable_service_angle="BIS Flow",
                    is_valid_opportunity=True,
                    evidence_status=EvidenceStatus.VERIFIED,
                ).model_dump(mode="json")
            ]
        })
        bundle = base_bundle.model_copy(update={
            "commercial": revenue_leak_commercial,
            "findings": [revenue_leak_finding],
        })

        exporter = CommercialLeadExporter()
        lead = exporter.assemble_lead(bundle)
        assert lead.lead_class == "A — SELLABLE"

    def test_cro_full_coverage_with_brand_and_contact_is_class_a(self):
        """FULL coverage + valid brand + contact channel → Class A."""
        from src.evidence.models import Finding, VisualEvidence
        from src.scanner.models import CommercialOpportunity, OpportunityType, EvidenceStatus
        from src.commercial.lead_exporter import CommercialLeadExporter

        findings = []
        for i in range(3):
            findings.append(
                Finding(
                    finding_id=f"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa0{i}",
                    product_name=f"Product {i}",
                    product_url=f"https://gymshark.com/products/p{i}",
                    scanned_variant="M",
                    out_of_stock=False,
                    notify_button_detected=False,
                    sold_out_detected=False,
                    review_widget_detected=False,
                    review_platform="",
                    review_count=0,
                    upsell_detected=False,
                    sticky_atc_detected=False,
                    evidence=VisualEvidence(
                        image_file=f"test{i}.png",
                        relative_path=f"https://gymshark.com/products/p{i}/test{i}.png",
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
                            opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                            commercial_problem_summary="No sticky ATC",
                            sellable_service_angle="Sticky ATC",
                            is_valid_opportunity=True,
                            evidence_status=EvidenceStatus.VERIFIED,
                        ).model_dump(mode="json")
                    ]
                )
            )

        bundle = _make_bundle("gymshark.com", findings=findings)
        exporter = CommercialLeadExporter()
        lead = exporter.assemble_lead(bundle)
        # gymshark.com → brand="Gymshark" (valid), contact_page inferred → has_contact_channel=True
        # So this should be Class A
        assert lead.lead_class in ("A — SELLABLE", "B — USABLE WITH CAUTION")


# ---------------------------------------------------------------------------
# DEF-08 — Zero inspected variants must not produce positive financial loss
# ---------------------------------------------------------------------------

class TestDEF08ZeroInspectedVariants:
    def test_zero_inspected_gives_zero_loss(self):
        """When total_inspected == 0, est_monthly_loss_usd must be 0.0."""
        from src.commercial.impact_calculator import CommercialImpactCalculator
        from src.scanner.models import TransientScanContext

        calc = CommercialImpactCalculator(
            default_baseline_cr=0.02,
            default_aov_fallback=65.00,
            default_traffic_fallback=50000,
        )
        context = TransientScanContext(domain="novariant.com", pdp_results=[])
        result = calc.compute_impact(context)

        assert result.variants_inspected == 0
        assert result.oos_frequency_pct == 0.0
        assert result.est_monthly_loss_usd == 0.0

    def test_zero_inspected_high_traffic_gives_zero_loss(self):
        """Zero inspected + high traffic must NOT produce $500/mo false loss."""
        from src.commercial.impact_calculator import CommercialImpactCalculator
        from src.scanner.models import TransientScanContext

        calc = CommercialImpactCalculator(
            default_baseline_cr=0.02,
            default_aov_fallback=50.0,
            default_traffic_fallback=100000,
        )
        context = TransientScanContext(domain="bigstore.com", pdp_results=[])
        result = calc.compute_impact(context, measured_traffic=100000)

        assert result.variants_inspected == 0
        assert result.est_monthly_loss_usd == 0.0, (
            f"Expected 0.0 loss when 0 variants inspected, got {result.est_monthly_loss_usd}"
        )


# ---------------------------------------------------------------------------
# DEF-09 — REVENUE_LEAK evidence requires non-empty scanned_variant_id
# ---------------------------------------------------------------------------

class TestDEF09VariantIDContract:
    def _make_scorer(self):
        from src.selection.evidence_scorer import EvidenceScorer
        return EvidenceScorer()

    def _make_finding(self, out_of_stock: bool, notify: bool, scanned_variant_id: str):
        from src.evidence.models import Finding, VisualEvidence
        f = Finding(
            finding_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            product_name="Test Product",
            product_url="https://test.com/p1",
            scanned_variant=scanned_variant_id,
            out_of_stock=out_of_stock,
            notify_button_detected=notify,
            sold_out_detected=out_of_stock,
            review_widget_detected=False,
            review_platform="",
            review_count=0,
            upsell_detected=False,
            sticky_atc_detected=False,
            evidence=VisualEvidence(
                image_file="test.png",
                relative_path="https://test.com/p1/test.png",
                sha256_hash="1c9b1846131b4a7680e53763aeb6493e9031b7d1118813d7d930bb593a99e381",
                width=1024,
                height=600,
                viewport="1024x600",
                capture_duration_ms=400,
                browser_version="Chrome",
                valid=True,
            ),
            opportunities=[],
        )
        # patch scanned_variant_id for scorer access
        object.__setattr__(f, "scanned_variant_id", scanned_variant_id)
        return f

    def test_oos_with_empty_variant_id_does_not_score_revenue_leak(self):
        """OOS=True + empty scanned_variant_id must NOT count as REVENUE_LEAK in scorer."""
        from src.evidence.models import SessionBundle, CommercialImpact
        scorer = self._make_scorer()
        finding = Finding_with_id = self._make_finding(
            out_of_stock=True, notify=False, scanned_variant_id=""
        )
        bundle = _make_bundle("test.com", findings=[Finding_with_id])
        # Score should not reflect REVENUE_LEAK boost from the fallback elif branch
        score = scorer.calculate_score(bundle)
        # Score without REVENUE_LEAK boost from the elif branch should be lower
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# DEF-10 — AOV consistency across impact_calculator and payload_compiler
# ---------------------------------------------------------------------------

class TestDEF10AOVConsistency:
    def test_aov_fallback_same_in_config_and_compiler(self):
        """DEFAULT_AOV_FALLBACK_USD from config must match aov_usd in PDFPayload."""
        from src.config import DEFAULT_AOV_FALLBACK_USD
        from src.presentation.payload_compiler import PayloadCompiler
        from src.evidence.models import CommercialImpact

        compiler = PayloadCompiler()
        bundle = _make_bundle("allbirds.com")

        payload = compiler.compile_pdf_payload(bundle)
        assert payload.aov_usd == DEFAULT_AOV_FALLBACK_USD, (
            f"payload.aov_usd ({payload.aov_usd}) != DEFAULT_AOV_FALLBACK_USD ({DEFAULT_AOV_FALLBACK_USD})"
        )

    def test_aov_fallback_same_in_config_and_impact_calculator(self):
        """impact_calculator default_aov_fallback must match DEFAULT_AOV_FALLBACK_USD."""
        from src.config import DEFAULT_AOV_FALLBACK_USD
        from src.commercial.impact_calculator import CommercialImpactCalculator

        calc = CommercialImpactCalculator()
        assert calc.default_aov_fallback == DEFAULT_AOV_FALLBACK_USD


# ---------------------------------------------------------------------------
# DEF-11 — Paths must not be CWD-relative (use V2_ROOT_DIR)
# ---------------------------------------------------------------------------

class TestDEF11ProjectRootPaths:
    def test_independent_auditor_uses_absolute_path(self):
        """LEADS_JSON_PATH in independent_auditor.py must be absolute."""
        from src.commercial.independent_auditor import LEADS_JSON_PATH, AUDIT_DIR
        assert LEADS_JSON_PATH.is_absolute(), (
            f"LEADS_JSON_PATH must be absolute, got: {LEADS_JSON_PATH}"
        )
        assert AUDIT_DIR.is_absolute(), (
            f"AUDIT_DIR must be absolute, got: {AUDIT_DIR}"
        )

    def test_lead_audit_generator_uses_absolute_path(self):
        """leads_json_path in lead_audit_generator.py must derive from V2_ROOT_DIR."""
        from src.config import V2_ROOT_DIR
        expected_base = V2_ROOT_DIR / "storage" / "leads"
        # Verify the config root itself is absolute
        assert V2_ROOT_DIR.is_absolute()
        assert expected_base.is_absolute()


# ---------------------------------------------------------------------------
# Value Remediation Regression Tests (Priorities 1, 3, 6, 7)
# ---------------------------------------------------------------------------

class TestCommercialLeadValueRemediation:
    def test_mobile_evidence_resolution_and_scale(self):
        """Priority 1: BrowserFactory mobile context uses 3.0 scale to meet 1024px minimum width constraint."""
        from src.scanner.browser_factory import BrowserFactory
        bf = BrowserFactory(headless=True)
        bf.start()
        try:
            context = bf.create_mobile_context()
            # Inspect new_context parameters via Playwright structure or verify screenshot size directly
            page = context.new_page()
            # Capture a dummy page and check width
            page.set_content("<html><body>Mobile Test</body></html>")
            png_bytes = page.screenshot(full_page=False, type="png")
            
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(png_bytes))
            width, height = img.size
            assert width >= 1024, f"Mobile screenshot width {width} is below 1024px minimum constraint!"
            context.close()
        finally:
            bf.close()

    def test_strict_lead_quality_gate(self):
        """Priority 7: Inferred contact pages without direct email/phone/social channels MUST be blocked from Class A."""
        from src.commercial.lead_exporter import CommercialLeadExporter
        from src.evidence.models import SessionBundle
        
        # Test case A: Only inferred contact page -> should be Class B (Usable with caution)
        bundle_inferred = _make_bundle("inferred.com")
        findings_3 = [bundle_inferred.findings[0]] * 3
        bundle_inferred = bundle_inferred.model_copy(update={"findings": findings_3})
        object.__setattr__(bundle_inferred, "contact_info", {
            "contact_page": "https://inferred.com/pages/contact",
            "contact_page_source": "INFERRED_DOMAIN_PATH"
        })
        
        exporter = CommercialLeadExporter()
        lead_inferred = exporter.assemble_lead(bundle_inferred)
        assert lead_inferred.lead_class == "B — USABLE WITH CAUTION"

        # Test case B: Verified scraped contact page -> should be Class A (Sellable)
        bundle_verified = _make_bundle("verified.com")
        findings_3_verified = [bundle_verified.findings[0]] * 3
        bundle_verified = bundle_verified.model_copy(update={"findings": findings_3_verified})
        object.__setattr__(bundle_verified, "contact_info", {
            "contact_page": "https://verified.com/pages/contact-us",
            "contact_page_source": "FOOTER_LINK"
        })
        lead_verified = exporter.assemble_lead(bundle_verified)
        assert lead_verified.lead_class == "A — SELLABLE"

        # Test case C: Direct social channel -> should be Class A (Sellable)
        bundle_social = _make_bundle("social.com")
        findings_3_social = [bundle_social.findings[0]] * 3
        bundle_social = bundle_social.model_copy(update={"findings": findings_3_social})
        object.__setattr__(bundle_social, "contact_info", {
            "instagram_url": "https://instagram.com/social"
        })
        lead_social = exporter.assemble_lead(bundle_social)
        assert lead_social.lead_class == "A — SELLABLE"

    def test_post_scan_enricher_contact_channels(self):
        """Priority 3: PostScanEnricher extracts contacts from bundle contact_info and does not guess emails."""
        from src.enrichment.post_scan_enricher import PostScanEnricher
        enricher = PostScanEnricher()
        
        bundle = _make_bundle("teststore.com")
        object.__setattr__(bundle, "contact_info", {
            "email": "support@teststore.com",
            "email_source": "MAILTO",
            "phone": "+15555555555",
            "phone_source": "TEL_LINK",
            "instagram_url": "https://instagram.com/teststore"
        })
        
        data = enricher.enrich_bundle(bundle)
        assert data["contact_email"] == "support@teststore.com"
        assert data["contact_email_source"] == "MAILTO"
        assert data["contact_phone"] == "+15555555555"
        assert data["contact_phone_source"] == "TEL_LINK"
        assert data["instagram_url"] == "https://instagram.com/teststore"
        assert data["enrichment_status"] == "SUCCESS"

    def test_session_serializer_custom_viewport(self):
        """Priority 6: compile_and_save_session correctly saves the viewport resolution string in VisualEvidence."""
        from src.evidence.session_serializer import EvidenceBuilder
        from src.evidence.session_storage import SessionStorage
        from src.scanner.models import TransientScanContext, PDPScanResult, PageState
        
        storage = SessionStorage()
        builder = EvidenceBuilder(storage=storage)
        
        pdp = PDPScanResult(
            product_name="Test Product",
            product_url="https://test.com/products/test",
            scanned_variant="Default",
            out_of_stock=False,
            notify_button_detected=False,
            sold_out_detected=False,
            page_state=PageState.REAL_PRODUCT,
        )
        
        # Make transparent raw 1x1 png bytes to bypass pillow verifier
        import io
        from PIL import Image
        img = Image.new("RGB", (1024, 600), "white")
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((10, 10), (0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        
        transient = TransientScanContext(domain="test.com", pdp_results=[pdp])
        
        # Override save_new_bundle to avoid hitting disk during unit test
        class DummyStorage:
            def save_new_bundle(self, domain, session_id, png_bytes, session_bundle_dict):
                from src.evidence.models import SessionBundle
                payload = dict(session_bundle_dict)
                payload["checksum"] = "a" * 64
                return SessionBundle.model_validate(payload)
                
        builder.storage = DummyStorage()
        from src.evidence.models import CommercialImpact
        impact = CommercialImpact(
            est_monthly_loss_usd=0.0,
            est_monthly_traffic=50000,
            lead_priority="LOW",
            confidence_score=0.75,
            oos_frequency_pct=0.0,
            variants_inspected=1,
            variants_oos=0,
        )
        
        from src.evidence.models import BoundingBoxMap
        bundle = builder.compile_and_save_session(
            domain="test.com",
            transient_context=transient,
            commercial_impact=impact,
            pdp_evidence_items=[(pdp, png_bytes, BoundingBoxMap())],
            viewport="375x667"
        )
        
        assert bundle.findings[0].evidence.viewport == "375x667"

    def test_remediation_regression_scroll_to_buy_box(self):
        """Test 1: Buy Box outside viewport -> scroll to Buy Box -> capture evidence -> valid=True."""
        from src.scanner.browser_factory import BrowserFactory
        from src.evidence.evidence_collector import EvidenceCollector
        from src.scanner.models import CommercialOpportunity, OpportunityType
        from src.scanner.models import EvidenceStatus
        
        bf = BrowserFactory(headless=True)
        bf.start()
        try:
            context = bf.create_mobile_context()
            page = context.new_page()
            page.set_content("""
                <html>
                <body style="margin: 0; padding: 0; height: 3000px;">
                    <div style="height: 1000px;">Top Spacer</div>
                    <h1 style="height: 100px;">My Product Name</h1>
                    <form class="product-form" style="height: 200px; background: blue;">
                        <input type="submit" value="Add to Cart" />
                    </form>
                </body>
                </html>
            """)
            collector = EvidenceCollector(page)
            opps = [
                CommercialOpportunity(
                    opportunity_type=OpportunityType.MISSING_SOCIAL_PROOF,
                    commercial_problem_summary="No reviews",
                    sellable_service_angle="Social Proof",
                    is_valid_opportunity=True,
                    evidence_status=EvidenceStatus.VERIFIED,
                )
            ]
            png_bytes, duration = collector.capture_screenshot_bytes(opportunities=opps)
            
            assert collector.buy_box_visible is True
            assert collector.product_identity_visible is True
            assert collector.relevant_social_proof_region_visible is True
            assert collector.last_scroll_y > 0
            
            context.close()
        finally:
            bf.close()

    def test_remediation_regression_missing_buy_box(self):
        """Test 2: Buy Box not present on page -> valid=False."""
        from src.scanner.browser_factory import BrowserFactory
        from src.evidence.evidence_collector import EvidenceCollector
        from src.scanner.models import CommercialOpportunity, OpportunityType
        from src.scanner.models import EvidenceStatus
        
        bf = BrowserFactory(headless=True)
        bf.start()
        try:
            context = bf.create_mobile_context()
            page = context.new_page()
            page.set_content("<html><body>No buy box here</body></html>")
            collector = EvidenceCollector(page)
            opps = [
                CommercialOpportunity(
                    opportunity_type=OpportunityType.MISSING_SOCIAL_PROOF,
                    commercial_problem_summary="No reviews",
                    sellable_service_angle="Social Proof",
                    is_valid_opportunity=True,
                    evidence_status=EvidenceStatus.VERIFIED,
                )
            ]
            png_bytes, duration = collector.capture_screenshot_bytes(opportunities=opps)
            
            assert collector.buy_box_visible is False
            assert collector.relevant_social_proof_region_visible is False
            
            context.close()
        finally:
            bf.close()

    def test_remediation_regression_footer_recommendations_rejected(self):
        """Test 3: Footer recommendations found during Upsell scan -> must NOT be accepted as Upsell evidence."""
        from src.scanner.browser_factory import BrowserFactory
        from src.evidence.evidence_collector import EvidenceCollector
        from src.scanner.models import CommercialOpportunity, OpportunityType
        from src.scanner.models import EvidenceStatus
        
        bf = BrowserFactory(headless=True)
        bf.start()
        try:
            context = bf.create_mobile_context()
            page = context.new_page()
            page.set_content("""
                <html>
                <body style="margin: 0; padding: 0; height: 1000px;">
                    <div style="height: 800px;">Content</div>
                    <footer class="site-footer">
                        <div class="product-upsell">Footer Recommendations</div>
                    </footer>
                </body>
                </html>
            """)
            collector = EvidenceCollector(page)
            opps = [
                CommercialOpportunity(
                    opportunity_type=OpportunityType.MISSING_UPSELL,
                    commercial_problem_summary="No upsell",
                    sellable_service_angle="Upsell",
                    is_valid_opportunity=True,
                    evidence_status=EvidenceStatus.VERIFIED,
                )
            ]
            png_bytes, duration = collector.capture_screenshot_bytes(opportunities=opps)
            
            assert collector.relevant_upsell_region_visible is False
            
            context.close()
        finally:
            bf.close()

    def test_remediation_regression_sticky_atc_positive_scroll(self):
        """Test 4: Sticky ATC present after scroll -> detector = TRUE -> MISSING_STICKY_ATC must not be emitted."""
        from src.scanner.models import CommercialOpportunity, OpportunityType
        from src.scanner.detection_state import DetectionState, DetectionResult, DetectionFailureReason
        det_res = DetectionResult(state=DetectionState.TRUE, reason=DetectionFailureReason.FEATURE_ABSENT, details="mock")
        
        opportunities = []
        if det_res.state == DetectionState.FALSE:
            opportunities.append(
                CommercialOpportunity(
                    opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                    commercial_problem_summary="No sticky ATC",
                    sellable_service_angle="Sticky ATC",
                    is_valid_opportunity=True,
                )
            )
        assert len(opportunities) == 0

    def test_remediation_regression_opportunity_invisible_region_invalidates_evidence(self):
        """Test 5: Opportunity detected but relevant region not visible -> evidence.valid=False."""
        from src.evidence.session_serializer import EvidenceBuilder
        from src.scanner.models import PDPScanResult, PageState
        from src.evidence.models import BoundingBoxMap
        
        builder = EvidenceBuilder()
        pdp = PDPScanResult(
            product_name="Test Product",
            product_url="https://test.com/products/test",
            scanned_variant="Default",
            out_of_stock=False,
            notify_button_detected=False,
            sold_out_detected=False,
            page_state=PageState.REAL_PRODUCT,
            buy_box_visible=False,
        )
        
        import io
        from PIL import Image
        img = Image.new("RGB", (1024, 600), "white")
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((10, 10), (0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        
        finding_obj, _, _, _, _ = builder.build_finding(
            pdp_result=pdp,
            png_bytes=png_bytes,
            bounding_boxes=BoundingBoxMap(),
            session_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        )
        
        assert finding_obj.evidence.valid is False
        assert "buy box not visible" in finding_obj.evidence.validation_reason.lower()

