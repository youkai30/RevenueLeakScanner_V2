"""
src/orchestration/production_runner.py — Production Batch Execution Engine

Layer 6: Production Orchestration Pool & Batch Manager
"""
import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.ingestion.store_loader import StoreLoader, StoreRecord
from src.ingestion.tenant_config import TenantConfig
from src.orchestration.models import BatchExecutionSummary, StoreExecutionResult, StoreExecutionStatus
from src.orchestration.worker import execute_single_store_worker

logger = logging.getLogger(__name__)


class ProductionScanOrchestrator:
    """
    Production Orchestrator running multi-store scans via ProcessPoolExecutor or sequential worker pool.
    
    GUARANTEES:
      - Store-level failure isolation (Store A failure does NOT crash Store B or C)
      - Configurable worker count (--workers 1 for debug/sequential, --workers N for process pool)
      - Dry-run mode support (--dry-run)
      - Structured execution summary generation
    """

    def __init__(self, num_workers: int = 1, tenant_config: TenantConfig | None = None) -> None:
        self.num_workers = max(1, num_workers)
        self.tenant_config = tenant_config or TenantConfig()

    def run_batch(
        self,
        stores: list[StoreRecord],
        dry_run: bool = False,
        max_retries: int = 2,
    ) -> BatchExecutionSummary:
        """Runs batch scanning across target store records."""
        batch_id = str(uuid4())
        start_timestamp = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        results: list[StoreExecutionResult] = []

        store_timeout_budget = getattr(self.tenant_config, "store_max_runtime_seconds", 180)

        if dry_run:

            logger.info("DRY-RUN MODE ENABLED. Validating %d target stores...", len(stores))
            for store in stores:
                results.append(
                    StoreExecutionResult(
                        domain=store.domain,
                        status=StoreExecutionStatus.SKIPPED,
                        duration_ms=0,
                        error_message="Dry-run execution enabled",
                    )
                )
        else:
            # Process-Isolated Worker Execution with hard wall-clock store timeout
            for store in stores:
                store_start = time.perf_counter()
                logger.info("[STORE START] %s (Time Budget: %ds)", store.domain, store_timeout_budget)

                res_dict = None
                with ProcessPoolExecutor(max_workers=1) as single_executor:
                    future = single_executor.submit(
                        execute_single_store_worker,
                        store.model_dump(mode="json"),
                        self.tenant_config.model_dump(mode="json"),
                        None,
                        max_retries,
                    )
                    try:
                        res_dict = future.result(timeout=store_timeout_budget)
                        results.append(StoreExecutionResult.model_validate(res_dict))
                        elapsed = time.perf_counter() - store_start
                        logger.info("[STORE COMPLETE] %s in %.2fs", store.domain, elapsed)
                    except Exception as exc:
                        elapsed = time.perf_counter() - store_start
                        # Check if timeout occurred
                        is_timeout = "TimeoutError" in exc.__class__.__name__ or isinstance(exc, TimeoutError)

                        # Terminate worker process tree to ensure no orphaned browser processes
                        try:
                            for pid in list(single_executor._processes.keys()):
                                try:
                                    import psutil
                                    parent = psutil.Process(pid)
                                    for child in parent.children(recursive=True):
                                        child.kill()
                                    parent.kill()
                                except ImportError:
                                    import os, subprocess
                                    if os.name == "nt":
                                        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    else:
                                        os.kill(pid, 9)
                                except Exception:
                                    pass
                            single_executor.shutdown(wait=False, cancel_futures=True)
                        except Exception:
                            pass

                        if is_timeout:
                            logger.warning(
                                "[STORE TIMEOUT] store=%s elapsed=%.1fs budget=%ds status=TIMEOUT reason=STORE_TIME_BUDGET_EXCEEDED",
                                store.domain, elapsed, store_timeout_budget
                            )
                            results.append(
                                StoreExecutionResult(
                                    domain=store.domain,
                                    status=StoreExecutionStatus.FAILED,
                                    duration_ms=int(elapsed * 1000),
                                    error_type="StoreTimeoutError",
                                    error_message=f"Store scan exceeded hard time budget of {store_timeout_budget}s",
                                    store_timeout=True,
                                    store_timeout_seconds=store_timeout_budget,
                                    store_elapsed_seconds=round(elapsed, 2),
                                    timeout_reason="STORE_TIME_BUDGET_EXCEEDED",
                                    timeout_phase="scanner_execution",
                                )
                            )
                        else:
                            logger.error("[STORE FAILED] %s: %s", store.domain, exc)
                            results.append(
                                StoreExecutionResult(
                                    domain=store.domain,
                                    status=StoreExecutionStatus.FAILED,
                                    duration_ms=int(elapsed * 1000),
                                    error_type=exc.__class__.__name__,
                                    error_message=str(exc),
                                )
                            )

                logger.info("[CLEANUP] %s resources terminated. Proceeding to next store.", store.domain)

        # Aggregate metrics
        total_duration = max(1, int((time.perf_counter() - start_time) * 1000))
        success_count = sum(1 for r in results if r.status == StoreExecutionStatus.SUCCESS)
        failed_count = sum(1 for r in results if r.status == StoreExecutionStatus.FAILED or r.status == StoreExecutionStatus.BLOCKED)
        skipped_count = sum(1 for r in results if r.status == StoreExecutionStatus.SKIPPED)

        total_stores = len(stores)
        success_rate = round((success_count / total_stores * 100.0), 2) if total_stores > 0 else 0.0

        # Automatic Commercial Lead Export for Current Run (NEW-01 Fix)
        if not dry_run:
            from src.commercial.lead_exporter import CommercialLeadExporter
            try:
                exporter = CommercialLeadExporter()
                exporter.export_current_run_leads(results)
                logger.info("Automatically exported current run commercial leads to storage/leads/leads.json and leads.csv")
            except Exception as exc:
                logger.error("Automatic commercial lead export failed for batch '%s': %s", batch_id, exc)
                raise RuntimeError(f"Automatic commercial lead export failed: {exc}") from exc

        return BatchExecutionSummary(
            batch_id=batch_id,
            timestamp_utc=start_timestamp,
            total_stores=total_stores,
            successful_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            success_rate_pct=success_rate,
            total_duration_ms=total_duration,
            results=results,
        )

