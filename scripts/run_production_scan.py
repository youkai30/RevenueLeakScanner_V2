"""
scripts/run_production_scan.py — CLI Batch Entry Point for Production Scans
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.store_loader import StoreLoader

from src.ingestion.tenant_config import TenantConfig
from src.orchestration.production_runner import ProductionScanOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_production_scan")


def main():
    parser = argparse.ArgumentParser(description="RevenueLeakScanner V2 — Master CLI Batch Scan Runner")
    parser.add_argument("--input", required=True, help="Path to input target stores CSV or JSON file")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Validate target stores without executing live scans")
    parser.add_argument("--retries", type=int, default=2, help="Maximum worker retries per store (default: 2)")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input target file not found: %s", input_path)
        sys.exit(1)

    loader = StoreLoader()
    stores = loader.load_stores_from_file(input_path)

    if not stores:
        logger.warning("No valid StoreRecord items loaded from input file.")
        sys.exit(0)

    logger.info("Loaded %d target store records from '%s'", len(stores), input_path)

    orchestrator = ProductionScanOrchestrator(num_workers=args.workers)
    summary = orchestrator.run_batch(stores=stores, dry_run=args.dry_run, max_retries=args.retries)

    print("\n" + "=" * 60)
    print("PRODUCTION SCAN COMPLETE")
    print("=" * 60)
    print(f"Batch ID:         {summary.batch_id}")
    print(f"Total Stores:     {summary.total_stores}")
    print(f"Successful:       {summary.successful_count}")
    print(f"Failed:           {summary.failed_count}")
    print(f"Skipped:          {summary.skipped_count}")
    print(f"Success Rate:     {summary.success_rate_pct:.1f}%")
    print(f"Total Duration:   {summary.total_duration_ms / 1000.0:.2f}s")
    print("=" * 60)

    if summary.failed_count > 0:
        print("\nFailed Stores:")
        for res in summary.results:
            if res.status.value == "FAILED":
                print(f" - {res.domain}: {res.error_type} — {res.error_message}")
        print("=" * 60)


if __name__ == "__main__":
    main()
