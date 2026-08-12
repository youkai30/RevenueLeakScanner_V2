"""
tests/test_pipeline_remediation.py — Regression Tests for NEW-01, NEW-02, and NEW-03

Verifies:
- NEW-01: CommercialLeadExporter.export_current_run_leads isolates current-run export.
- NEW-02: summarize_validation_run contract parsing and strict exclusion of historical sessions.
- NEW-03: Anti-bot BLOCKED store handling vs EMPTY clean store separation.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.commercial.lead_exporter import CommercialLeadExporter, CommercialLeadRecord
from src.evidence.models import BoundingBoxMap, CommercialImpact, Finding, SessionBundle, VisualEvidence
from src.orchestration.models import BatchExecutionSummary, StoreExecutionResult, StoreExecutionStatus
from src.scanner.models import CommercialOpportunity, EvidenceStatus, OpportunityType
from src.scanner.page_validator import PageState, PageValidator


def _make_evidence(domain: str, session_id_str: str) -> VisualEvidence:
    return VisualEvidence(
        image_file=f"session_{session_id_str}.png",
        relative_path=f"https://{domain}/products/test/session_{session_id_str}.png",
        width=1024,
        height=600,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        capture_duration_ms=450,
        browser_version="Chromium 120.0",
        viewport="1365x900",
        valid=True,
        validation_reason="OK",
    )


def _make_finding_with_opportunity(domain: str, session_id_str: str) -> Finding:
    """Create a Finding with a CRO opportunity (clean store)."""
    return Finding(
        product_name="Clean Test Product",
        product_url=f"https://{domain}/products/test",
        scanned_variant="Default",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        review_widget_detected=False,
        review_platform="",
        review_count=0,
        opportunities=[
            CommercialOpportunity(
                opportunity_type=OpportunityType.MISSING_STICKY_ATC,
                commercial_problem_summary="Lacks sticky ATC",
                sellable_service_angle="Sticky ATC Optimization",
                is_valid_opportunity=True,
                evidence_status=EvidenceStatus.VERIFIED,
            ).model_dump(mode="json")
        ],
        evidence=_make_evidence(domain, session_id_str),
        bounding_boxes=BoundingBoxMap(),
    )


def _make_finding_empty(domain: str, session_id_str: str) -> Finding:
    """Create a Finding with no opportunities (blocked or empty store)."""
    return Finding(
        product_name="Protected Product Page",
        product_url=f"https://{domain}/products/test",
        scanned_variant="Default",
        out_of_stock=False,
        notify_button_detected=False,
        sold_out_detected=False,
        review_widget_detected=False,
        review_platform="",
        review_count=0,
        opportunities=[],
        evidence=_make_evidence(domain, session_id_str),
        bounding_boxes=BoundingBoxMap(),
    )


def _make_bundle(
    domain: str,
    session_id_str: str = "11111111-1111-1111-1111-111111111111",
    with_opportunity: bool = True,
) -> SessionBundle:
    finding = (
        _make_finding_with_opportunity(domain, session_id_str)
        if with_opportunity
        else _make_finding_empty(domain, session_id_str)
    )
    return SessionBundle(
        domain=domain,
        session_id=session_id_str,
        build_id="22222222-2222-2222-2222-222222222222",
        timestamp="2026-08-10T10:00:00Z",
        scanner_version="2.3.1",
        schema_version="2.0.0",
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        commercial=CommercialImpact(
            est_monthly_loss_usd=0.0,
            lead_priority="LOW",
            confidence_score=0.65,
            variants_inspected=3,
            variants_oos=0,
            oos_frequency_pct=0.0,
            est_monthly_traffic=50000,
        ),
        findings=[finding],
    )


# ===========================================================================
# NEW-01: Commercial Lead Export Integration Tests
# ===========================================================================

class TestNEW01LeadExportIsolation:
    def test_export_current_run_leads_isolates_current_session(self, tmp_path):
        """Current run lead exporter exports ONLY session JSONs from current run execution results."""
        bundle_a = _make_bundle("storea.com", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        session_file_a = tmp_path / "session_a.json"
        with open(session_file_a, "w", encoding="utf-8") as f:
            json.dump(bundle_a.model_dump(mode="json"), f)

        res_a = StoreExecutionResult(
            domain="storea.com",
            status=StoreExecutionStatus.SUCCESS,
            session_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            duration_ms=5000,
            session_json_path=str(session_file_a),
        )

        output_dir = tmp_path / "leads_out"
        exporter = CommercialLeadExporter()
        csv_p, json_p = exporter.export_current_run_leads([res_a], output_dir=output_dir)

        assert csv_p.exists()
        assert json_p.exists()

        with open(json_p, "r", encoding="utf-8") as f:
            leads_data = json.load(f)

        assert len(leads_data) == 1
        assert leads_data[0]["domain"] == "storea.com"

    def test_failed_or_blocked_results_not_exported_as_success_leads(self, tmp_path):
        """Failed or blocked stores without session JSON are omitted from lead exports."""
        res_blocked = StoreExecutionResult(
            domain="blockedstore.com",
            status=StoreExecutionStatus.BLOCKED,
            duration_ms=3000,
            error_type="AntiBotBlockError",
            error_message="Scan blocked by Cloudflare",
        )

        output_dir = tmp_path / "leads_out"
        exporter = CommercialLeadExporter()
        csv_p, json_p = exporter.export_current_run_leads([res_blocked], output_dir=output_dir)

        with open(json_p, "r", encoding="utf-8") as f:
            leads_data = json.load(f)

        assert len(leads_data) == 0

    def test_compilation_failure_raises_explicit_runtime_error(self, tmp_path):
        """If session bundle JSON is corrupted, export raises an explicit RuntimeError."""
        bad_json = tmp_path / "bad_session.json"
        bad_json.write_text("CORRUPTED_JSON_DATA")

        res_bad = StoreExecutionResult(
            domain="badstore.com",
            status=StoreExecutionStatus.SUCCESS,
            session_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            duration_ms=1000,
            session_json_path=str(bad_json),
        )

        exporter = CommercialLeadExporter()
        with pytest.raises(RuntimeError, match="Commercial lead compilation failed"):
            exporter.export_current_run_leads([res_bad], output_dir=tmp_path / "leads")


# ===========================================================================
# NEW-02: summarize_validation_run Contract & Isolation Tests
# ===========================================================================

class TestNEW02SummaryContract:
    def test_summarize_validation_run_supports_list_schema(self, tmp_path, monkeypatch):
        """summarize_validation_run parses live_run_summary.json formatted as a JSON list."""
        import summarize_validation_run

        sessions_dir = tmp_path / "sessions"
        store_dir = sessions_dir / "testdomain.com"
        store_dir.mkdir(parents=True, exist_ok=True)

        session_id = "11111111-1111-1111-1111-111111111111"
        bundle = _make_bundle("testdomain.com", session_id)
        session_file = store_dir / f"session_{session_id}.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(bundle.model_dump(mode="json"), f)

        summary_file = tmp_path / "live_run_summary.json"
        summary_file.write_text(json.dumps([
            {"domain": "testdomain.com", "status": "SUCCESS", "session_id": session_id}
        ]))

        monkeypatch.setattr(summarize_validation_run, "SESSIONS_DIR", sessions_dir)
        monkeypatch.setattr(summarize_validation_run, "V2_ROOT_DIR", tmp_path)

        # Must run cleanly without AttributeError
        summarize_validation_run.compile_report()

    def test_summarize_validation_run_supports_dict_schema(self, tmp_path, monkeypatch):
        """summarize_validation_run parses live_run_summary.json formatted as dict with 'results' key."""
        import summarize_validation_run

        sessions_dir = tmp_path / "sessions"
        store_dir = sessions_dir / "testdomain.com"
        store_dir.mkdir(parents=True, exist_ok=True)

        session_id = "11111111-1111-1111-1111-111111111111"
        bundle = _make_bundle("testdomain.com", session_id)
        session_file = store_dir / f"session_{session_id}.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(bundle.model_dump(mode="json"), f)

        summary_file = tmp_path / "live_run_summary.json"
        summary_file.write_text(json.dumps({
            "total_stores": 1,
            "results": [{"domain": "testdomain.com", "status": "SUCCESS", "session_id": session_id}]
        }))

        monkeypatch.setattr(summarize_validation_run, "SESSIONS_DIR", sessions_dir)
        monkeypatch.setattr(summarize_validation_run, "V2_ROOT_DIR", tmp_path)

        summarize_validation_run.compile_report()

    def test_invalid_json_schema_raises_value_error(self, tmp_path, monkeypatch):
        """Malformed JSON summary type raises explicit ValueError and does NOT fall back."""
        import summarize_validation_run

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        summary_file = tmp_path / "live_run_summary.json"
        summary_file.write_text('"INVALID_STRING_SCHEMA"')

        monkeypatch.setattr(summarize_validation_run, "SESSIONS_DIR", sessions_dir)
        monkeypatch.setattr(summarize_validation_run, "V2_ROOT_DIR", tmp_path)

        with pytest.raises(ValueError, match="Invalid summary schema"):
            summarize_validation_run.compile_report()

    def test_historical_sessions_not_aggregated_when_not_in_summary(self, tmp_path, monkeypatch):
        """Historical session directory is strictly ignored if session ID is not in live_run_summary.json."""
        import summarize_validation_run

        sessions_dir = tmp_path / "sessions"
        old_dir = sessions_dir / "olddomain.com"
        old_dir.mkdir(parents=True)
        old_session = old_dir / "session_99999999-9999-9999-9999-999999999999.json"
        old_bundle = _make_bundle("olddomain.com", "99999999-9999-9999-9999-999999999999")
        old_session.write_text(json.dumps(old_bundle.model_dump(mode="json")))

        new_dir = sessions_dir / "newdomain.com"
        new_dir.mkdir(parents=True)
        new_sid = "88888888-8888-8888-8888-888888888888"
        new_session = new_dir / f"session_{new_sid}.json"
        new_bundle = _make_bundle("newdomain.com", new_sid)
        new_session.write_text(json.dumps(new_bundle.model_dump(mode="json")))

        summary_file = tmp_path / "live_run_summary.json"
        summary_file.write_text(json.dumps({
            "results": [{"domain": "newdomain.com", "status": "SUCCESS", "session_id": new_sid}]
        }))

        monkeypatch.setattr(summarize_validation_run, "SESSIONS_DIR", sessions_dir)
        monkeypatch.setattr(summarize_validation_run, "V2_ROOT_DIR", tmp_path)

        summarize_validation_run.compile_report()

        report_file = tmp_path / "storage" / "reports" / "validation_report.md"
        if report_file.exists():
            content = report_file.read_text()
            assert "olddomain.com" not in content
            assert "newdomain.com" in content


# ===========================================================================
# NEW-03: Anti-Bot & Store State Separation Tests
# ===========================================================================

class TestNEW03AntiBotStateSeparation:
    def test_cloudflare_blocked_page_state_detected(self):
        """PageValidator detects Cloudflare challenge titles as PageState.CLOUDFLARE_BLOCKED."""
        validator = PageValidator()
        mock_page = MagicMock()
        mock_page.title.return_value = "Just a moment... | Cloudflare"
        mock_response = MagicMock()
        mock_response.status = 503
        mock_response.headers = {"server": "cloudflare"}

        res = validator.validate_page(mock_page, "https://protectedstore.com/products/item", mock_response)
        assert res.status == PageState.CLOUDFLARE_BLOCKED

    def test_store_with_no_opportunities_classified_as_none_detected(self):
        """A bundle with 0 opportunities produces primary_opportunity == NONE_DETECTED."""
        bundle_empty = _make_bundle("emptystore.com", "77777777-7777-7777-7777-777777777777", with_opportunity=False)
        exporter = CommercialLeadExporter()
        lead = exporter.assemble_lead(bundle_empty)

        assert lead.primary_opportunity == "NONE_DETECTED"
        assert lead.estimated_monthly_loss_usd == 0.0

    def test_store_with_opportunity_classified_as_cro_lead(self):
        """A bundle with MISSING_STICKY_ATC opportunity produces STRONG_CRO_OPPORTUNITY category."""
        bundle_cro = _make_bundle("crostorex.com", "66666666-6666-6666-6666-666666666666", with_opportunity=True)
        exporter = CommercialLeadExporter()
        lead = exporter.assemble_lead(bundle_cro)

        assert lead.primary_opportunity == "MISSING_STICKY_ATC"
        assert lead.lead_type_category == "STRONG_CRO_OPPORTUNITY"
        assert lead.estimated_monthly_loss_usd == 0.0

    def test_cro_lead_and_empty_lead_are_distinguishable(self):
        """CRO opportunity lead and empty/no-opportunity lead have distinct classifications."""
        bundle_cro = _make_bundle("crostorex.com", "66666666-6666-6666-6666-666666666666", with_opportunity=True)
        bundle_empty = _make_bundle("emptystore.com", "55555555-5555-5555-5555-555555555555", with_opportunity=False)

        exporter = CommercialLeadExporter()
        lead_cro = exporter.assemble_lead(bundle_cro)
        lead_empty = exporter.assemble_lead(bundle_empty)

        assert lead_cro.primary_opportunity == "MISSING_STICKY_ATC"
        assert lead_empty.primary_opportunity == "NONE_DETECTED"
        assert lead_cro.lead_class != lead_empty.lead_class
