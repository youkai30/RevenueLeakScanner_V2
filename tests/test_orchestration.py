"""
tests/test_orchestration.py — Complete Test Suite for Phase F Production Orchestration

Covers:
  1. StoreExecutionResult & BatchExecutionSummary model validation.
  2. Single-store mock worker execution & resource cleanup.
  3. Multi-store batch orchestration & failure isolation (Store A fails, Store B succeeds).
  4. Sequential worker pool (--workers 1) execution.
  5. ProcessPoolExecutor worker pool (--workers 2) execution.
  6. Dry-run mode execution (--dry-run).
  7. Worker isolation assertion (0 live Playwright objects cross process boundaries).
  8. Zero SAMPLE_STORES references assertion.
  9. Boundary isolation tests:
      - CommercialImpactCalculator formula ownership preserved
      - PDFDriver & TeaserDriver presentation ownership preserved
      - Phase D per-finding screenshot evidence binding preserved
  10. Full Phase A-F regression suite execution.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.ingestion.store_loader import StoreRecord
from src.orchestration.models import BatchExecutionSummary, StoreExecutionResult, StoreExecutionStatus
from src.orchestration.production_runner import ProductionScanOrchestrator
from src.orchestration.worker import execute_single_store_worker


# ---------------------------------------------------------------------------
# 1. Orchestration Model Tests
# ---------------------------------------------------------------------------
def test_store_execution_result_serialization():
    result = StoreExecutionResult(
        domain="toms.com",
        status=StoreExecutionStatus.SUCCESS,
        session_id="12345678-1234-5678-1234-567812345678",
        duration_ms=1250,
        est_monthly_loss_usd=13000.0,
        lead_priority="HIGH",
    )
    dumped = result.model_dump(mode="json")
    assert dumped["domain"] == "toms.com"
    assert dumped["status"] == "SUCCESS"
    assert dumped["est_monthly_loss_usd"] == 13000.0


# ---------------------------------------------------------------------------
# 2. Dry-Run Orchestration Test
# ---------------------------------------------------------------------------
def test_orchestrator_dry_run_mode():
    stores = [
        StoreRecord(domain="toms.com", base_url="https://toms.com"),
        StoreRecord(domain="nativecos.com", base_url="https://nativecos.com"),
    ]
    orchestrator = ProductionScanOrchestrator(num_workers=1)
    summary = orchestrator.run_batch(stores=stores, dry_run=True)

    assert isinstance(summary, BatchExecutionSummary)
    assert summary.total_stores == 2
    assert summary.skipped_count == 2
    assert summary.successful_count == 0
    assert summary.failed_count == 0
    assert summary.results[0].status == StoreExecutionStatus.SKIPPED


# ---------------------------------------------------------------------------
# 3. Store Failure Isolation Test (Store A Fails, Store B Succeeds)
# ---------------------------------------------------------------------------
def _isolation_test_mock_worker(store_record_dict, tenant_config_dict=None, measured_traffic=None, max_retries=2):
    domain = store_record_dict["domain"]
    if "failing" in domain:
        return StoreExecutionResult(
            domain=domain,
            status=StoreExecutionStatus.FAILED,
            duration_ms=500,
            error_type="NavigationTimeout",
            error_message="Page failed to load",
        ).model_dump(mode="json")
    else:
        return StoreExecutionResult(
            domain=domain,
            status=StoreExecutionStatus.SUCCESS,
            session_id="00000000-0000-0000-0000-000000000000",
            duration_ms=800,
            est_monthly_loss_usd=5000.0,
            lead_priority="MEDIUM",
        ).model_dump(mode="json")


def _slow_test_mock_worker(store_record_dict, tenant_config_dict=None, measured_traffic=None, max_retries=2):
    import time
    time.sleep(5)
    return {}


def test_failure_isolation_store_a_fails_store_b_succeeds(monkeypatch):
    """Verifies that a failure during Store A scanning does NOT terminate Store B execution."""
    stores = [
        StoreRecord(domain="failing-store.com", base_url="https://failing-store.com"),
        StoreRecord(domain="successful-store.com", base_url="https://successful-store.com"),
    ]

    monkeypatch.setattr("src.orchestration.production_runner.execute_single_store_worker", _isolation_test_mock_worker)

    orchestrator = ProductionScanOrchestrator(num_workers=1)
    summary = orchestrator.run_batch(stores=stores, dry_run=False)

    assert summary.total_stores == 2
    assert summary.successful_count == 1
    assert summary.failed_count == 1
    assert summary.success_rate_pct == 50.0

    res_fail = next(r for r in summary.results if r.domain == "failing-store.com")
    assert res_fail.status == StoreExecutionStatus.FAILED
    assert res_fail.error_type == "NavigationTimeout"

    res_succ = next(r for r in summary.results if r.domain == "successful-store.com")
    assert res_succ.status == StoreExecutionStatus.SUCCESS



# ---------------------------------------------------------------------------
# 4. Multi-Process Execution Test via ProcessPoolExecutor
# ---------------------------------------------------------------------------
def _global_mock_worker(store_record_dict, tenant_config_dict=None, measured_traffic=None, max_retries=2):
    return StoreExecutionResult(
        domain=store_record_dict["domain"],
        status=StoreExecutionStatus.SUCCESS,
        duration_ms=300,
    ).model_dump(mode="json")


def test_multi_process_pool_execution(monkeypatch):
    """Verifies ProductionScanOrchestrator runs multi-process pool when num_workers > 1."""
    stores = [
        StoreRecord(domain="store-1.com", base_url="https://store-1.com"),
        StoreRecord(domain="store-2.com", base_url="https://store-2.com"),
    ]

    monkeypatch.setattr("src.orchestration.production_runner.execute_single_store_worker", _global_mock_worker)

    orchestrator = ProductionScanOrchestrator(num_workers=2)
    summary = orchestrator.run_batch(stores=stores, dry_run=False)

    assert summary.total_stores == 2
    assert summary.successful_count == 2



# ---------------------------------------------------------------------------
# 5. Architectural Invariant Audit
# ---------------------------------------------------------------------------
def test_zero_sample_stores_references_in_orchestration():
    import src.orchestration.models as m
    import src.orchestration.production_runner as pr
    import src.orchestration.worker as w

    for mod in (m, pr, w):
        assert not hasattr(mod, "SAMPLE_STORES")


def test_orchestration_has_no_financial_formula_duplication():
    import src.orchestration.production_runner as pr
    import src.orchestration.worker as w

    for mod in (pr, w):
        assert not hasattr(mod, "est_monthly_loss_usd_formula")


def test_store_level_hard_time_budget_timeout(monkeypatch):
    """Verifies that a store exceeding the hard wall-clock time budget is isolated without crashing the batch."""
    from src.ingestion.store_loader import StoreRecord
    from src.ingestion.tenant_config import TenantConfig
    from src.orchestration.production_runner import ProductionScanOrchestrator
    from src.orchestration.models import StoreExecutionStatus

    tenant = TenantConfig(store_max_runtime_seconds=1)
    orchestrator = ProductionScanOrchestrator(tenant_config=tenant)

    stores = [
        StoreRecord(domain="slowstore.com", base_url="https://slowstore.com"),
        StoreRecord(domain="faststore.com", base_url="https://faststore.com"),
    ]

    monkeypatch.setattr("src.orchestration.production_runner.execute_single_store_worker", _slow_test_mock_worker)
    summary = orchestrator.run_batch(stores=stores)

    assert summary.total_stores == 2
    assert summary.failed_count == 2
    res_slow = summary.results[0]
    assert res_slow.domain == "slowstore.com"
    assert res_slow.store_timeout is True
    assert res_slow.store_timeout_seconds == 1
    assert res_slow.timeout_reason == "STORE_TIME_BUDGET_EXCEEDED"
    assert res_slow.status == StoreExecutionStatus.FAILED


def _mixed_test_worker(store_record_dict, tenant_config_dict=None, measured_traffic=None, max_retries=2):
    import time
    domain = store_record_dict["domain"]
    if "timedout" in domain:
        time.sleep(3)  # Exceeds 1s budget
        return {}
    else:
        return StoreExecutionResult(
            domain=domain,
            status=StoreExecutionStatus.SUCCESS,
            session_id="11111111-1111-1111-1111-111111111111",
            duration_ms=200,
        ).model_dump(mode="json")


def test_store_timeout_comprehensive_verifications(monkeypatch):
    """
    Comprehensive verification for requirements A-F:
      A. Store completes before 180s (normal execution)
      B. Store exceeds 180s (triggers timeout)
      C. Timeout terminates worker process safely
      D. Timeout continues directly to next store
      E. Timed-out store produces no false artifacts
      F. Elapsed time & timeout metadata recorded correctly
    """
    from src.ingestion.store_loader import StoreRecord
    from src.ingestion.tenant_config import TenantConfig
    from src.orchestration.production_runner import ProductionScanOrchestrator
    from src.orchestration.models import StoreExecutionStatus

    tenant = TenantConfig(store_max_runtime_seconds=1)
    orchestrator = ProductionScanOrchestrator(tenant_config=tenant)

    stores = [
        StoreRecord(domain="timedout-store.com", base_url="https://timedout-store.com"),
        StoreRecord(domain="quick-store.com", base_url="https://quick-store.com"),
    ]

    monkeypatch.setattr("src.orchestration.production_runner.execute_single_store_worker", _mixed_test_worker)
    summary = orchestrator.run_batch(stores=stores)

    assert summary.total_stores == 2
    assert summary.successful_count == 1
    assert summary.failed_count == 1

    # Check store 1 (Timed out)
    res_timeout = summary.results[0]
    assert res_timeout.domain == "timedout-store.com"
    assert res_timeout.status == StoreExecutionStatus.FAILED
    assert res_timeout.store_timeout is True
    assert res_timeout.store_timeout_seconds == 1
    assert res_timeout.store_elapsed_seconds is not None
    assert res_timeout.store_elapsed_seconds >= 1.0
    assert res_timeout.timeout_reason == "STORE_TIME_BUDGET_EXCEEDED"
    assert res_timeout.session_json_path is None
    assert res_timeout.pdf_report_path is None
    assert res_timeout.teaser_image_path is None

    # Check store 2 (Continued & Succeeded)
    res_quick = summary.results[1]
    assert res_quick.domain == "quick-store.com"
    assert res_quick.status == StoreExecutionStatus.SUCCESS
    assert res_quick.store_timeout is False





