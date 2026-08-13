"""
run_live_scan.py — Live Real-World Scanner Runner with Concurrency Support
"""
import argparse
import concurrent.futures
import logging
import json
import time
from pathlib import Path
from src.ingestion.store_loader import StoreLoader
from src.orchestration.worker import execute_single_store_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default if None or invalid."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value, default: str = "N/A") -> str:
    """Safely convert a value to string, returning default if None or empty."""
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def scan_single_store_task(item):
    idx, total, store = item
    print(f"\n---> [{idx}/{total}] STARTING Domain: {store.domain} ({store.base_url})")
    start_t = time.perf_counter()
    try:
        res_dict = execute_single_store_worker(store.model_dump(mode="json"))
        elapsed = time.perf_counter() - start_t

        # SAFE EXTRACTION — handles None values from failed scans
        status = _safe_str(res_dict.get("status"), "UNKNOWN")
        session_id = _safe_str(res_dict.get("session_id"), "N/A")
        session_json_path = _safe_str(res_dict.get("session_json_path"), "N/A")
        est_loss = _safe_float(res_dict.get("est_monthly_loss_usd"), 0.0)
        lead_priority = _safe_str(res_dict.get("lead_priority"), "N/A")

        print(
            f"\n---> [{idx}/{total}] COMPLETED Domain: {store.domain} in {elapsed:.1f}s\n"
            f"     Status: {status}\n"
            f"     Session ID: {session_id}\n"
            f"     Estimated Monthly Loss: ${est_loss:,.2f}\n"
            f"     Lead Priority: {lead_priority}\n"
            f"     Session JSON: {session_json_path}"
        )
        return res_dict
    except Exception as exc:
        logger.error("Failed scanning store %s: %s", store.domain, exc)
        return {
            "domain": store.domain,
            "status": "FAILED",
            "error_message": str(exc),
            "est_monthly_loss_usd": 0.0,
            "lead_priority": "N/A",
        }


def main():
    parser = argparse.ArgumentParser(description="Live Real-World Scanner Runner")
    parser.add_argument("--csv", type=str, default="stores.csv", help="Path to stores CSV file")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers (default: 1)")
    args = parser.parse_args()

    csv_file = Path(args.csv)
    if not csv_file.exists():
        logger.error("Stores file '%s' not found!", args.csv)
        return

    loader = StoreLoader()
    store_records = loader.load_stores_from_file(csv_file)
    logger.info("Loaded %d target stores from '%s'", len(store_records), args.csv)

    summary_results = []
    total = len(store_records)

    print("\n==================================================")
    print(f"STARTING LIVE SCAN FOR {total} STORES (workers={args.workers})")
    print("==================================================\n")

    tasks = [(idx, total, store) for idx, store in enumerate(store_records, start=1)]

    if args.workers <= 1:
        # Sequential Execution
        for task in tasks:
            res = scan_single_store_task(task)
            summary_results.append(res)
    else:
        # Concurrent Thread Pool Execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(scan_single_store_task, task): task for task in tasks}
            for future in concurrent.futures.as_completed(futures):
                try:
                    res = future.result()
                    summary_results.append(res)
                except Exception as exc:
                    logger.error("Task generated an unhandled exception: %s", exc)

    # Export leads via CommercialLeadExporter
    from src.commercial.lead_exporter import CommercialLeadExporter
    try:
        exporter = CommercialLeadExporter()
        exporter.export_current_run_leads(summary_results)
        logger.info("Exported commercial leads to storage/leads/leads.json and leads.csv")
    except Exception as exc:
        logger.error("Failed automatic lead export in run_live_scan: %s", exc)

    summary_payload = {
        "total_stores": len(store_records),
        "results": summary_results,
    }
    with open("live_run_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    print("\n==================================================")
    print("LIVE SCAN COMPLETED FOR ALL STORES")
    print("Summary written to 'live_run_summary.json'")
    print("Commercial leads written to 'storage/leads/leads.json' and 'leads.csv'")
    print("==================================================\n")


if __name__ == "__main__":
    main()
