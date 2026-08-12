"""
summarize_validation_run.py — Detailed Validation Report Compiler

Parses the generated session JSON files from the latest validation run,
aggregates all metrics required by user request, prints detailed per-PDP lists,
and saves a comprehensive markdown audit report.
"""
import json
import logging
from pathlib import Path
from datetime import datetime

from src.config import V2_ROOT_DIR, SESSIONS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def compile_report():
    sessions_dir = SESSIONS_DIR
    if not sessions_dir.exists():
        logger.error("storage/sessions directory does not exist! Please run live scan first.")
        return
    summary_file = V2_ROOT_DIR / "live_run_summary.json"
    allowed_session_ids = set()
    allowed_domains = set()
    summary_file_present = summary_file.exists()

    if summary_file_present:
        try:
            with open(summary_file, "r", encoding="utf-8") as sf:
                summary_data = json.load(sf)
            
            results_list = []
            if isinstance(summary_data, dict):
                if "results" in summary_data and isinstance(summary_data["results"], list):
                    results_list = summary_data["results"]
                else:
                    raise ValueError("Invalid summary schema: dict must contain a 'results' list.")
            elif isinstance(summary_data, list):
                results_list = summary_data
            else:
                raise ValueError(f"Invalid summary schema: expected dict or list, got {type(summary_data).__name__}")

            for res in results_list:
                if isinstance(res, dict):
                    if res.get("domain"):
                        allowed_domains.add(str(res["domain"]).lower())
                    if res.get("session_id"):
                        allowed_session_ids.add(str(res["session_id"]))
        except Exception as exc:
            logger.error("Failed parsing live_run_summary.json contract: %s", exc)
            raise ValueError(f"Failed parsing live_run_summary.json contract: {exc}") from exc

    # Find matching session JSON files for current run strictly
    latest_files = []
    for domain_path in sessions_dir.iterdir():
        if domain_path.is_dir():
            domain_name = domain_path.name.lower()
            if allowed_domains and domain_name not in allowed_domains:
                continue

            json_files = list(domain_path.glob("**/*.json"))
            if json_files:
                json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                if summary_file_present:
                    # Strict matching against current run session IDs — NO fallback to historical sessions!
                    for jf in json_files:
                        if any(sid in jf.name for sid in allowed_session_ids):
                            latest_files.append(jf)
                            break
                else:
                    latest_files.append(json_files[0])

    if not latest_files:
        logger.error("No session JSON files matching current run found!")
        return

    logger.info("Found %d session files to aggregate.", len(latest_files))

    pdp_rows = []
    
    # Aggregates
    stores_scanned = len(latest_files)
    pdps_scanned = 0
    variants_inspected = 0
    variant_ids_found = 0
    oos_true_count = 0
    bis_true_count = 0
    review_true_count = 0
    review_false_count = 0
    review_unknown_count = 0
    upsell_true_count = 0
    upsell_false_count = 0
    upsell_unknown_count = 0
    sticky_true_count = 0
    sticky_false_count = 0
    sticky_unknown_count = 0
    revenue_leak_count = 0
    missing_social_proof_count = 0
    missing_upsell_count = 0
    missing_sticky_atc_count = 0
    screenshots_captured = 0
    errors = 0

    for session_file in latest_files:
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            domain = data.get("domain", "")
            findings = data.get("findings", [])
            commercial = data.get("commercial", {})

            variants_inspected += commercial.get("variants_inspected", 0)
            
            for finding in findings:
                pdps_scanned += 1
                
                url = finding.get("product_url", "")
                
                # Bboxes, validation reasons represent page/evidence status
                evidence = finding.get("evidence", {})
                valid = evidence.get("valid", False)
                page_state = "REAL_PRODUCT" if valid else "UNKNOWN"
                if evidence:
                    screenshots_captured += 1
                
                out_of_stock = finding.get("out_of_stock", False)
                scanned_variant = finding.get("scanned_variant", "")
                scanned_variant_id = finding.get("scanned_variant_id", "")
                
                if out_of_stock:
                    oos_true_count += 1
                if scanned_variant_id:
                    variant_ids_found += 1
                
                notify_button_detected = finding.get("notify_button_detected", False)
                sold_out_detected = finding.get("sold_out_detected", False)
                if notify_button_detected:
                    bis_true_count += 1

                review_widget_detected = finding.get("review_widget_detected", False)
                review_platform = finding.get("review_platform", "")
                # Infer CRO stack detection states
                # (Since locked core_scanner converts TRUE/FALSE/UNKNOWN internally)
                # If widget detected -> TRUE. If not detected but count is 0, check opportunities.
                opp_types = [opp.get("opportunity_type") for opp in finding.get("opportunities", [])]
                
                # Review state
                if review_widget_detected:
                    review_state = "TRUE"
                    review_true_count += 1
                elif "MISSING_SOCIAL_PROOF" in opp_types:
                    review_state = "FALSE"
                    review_false_count += 1
                    missing_social_proof_count += 1
                else:
                    review_state = "UNKNOWN"
                    review_unknown_count += 1

                # Upsell state
                upsell_detected = finding.get("upsell_detected", False)
                if upsell_detected:
                    upsell_state = "TRUE"
                    upsell_true_count += 1
                elif "MISSING_UPSELL" in opp_types:
                    # Note: missing_upsell doesn't add to Class A by contract but can exist
                    upsell_state = "FALSE"
                    upsell_false_count += 1
                    missing_upsell_count += 1
                else:
                    upsell_state = "UNKNOWN"
                    upsell_unknown_count += 1

                # Sticky ATC state
                sticky_atc_detected = finding.get("sticky_atc_detected", False)
                if sticky_atc_detected:
                    sticky_atc_state = "TRUE"
                    sticky_true_count += 1
                elif "MISSING_STICKY_ATC" in opp_types:
                    sticky_atc_state = "FALSE"
                    sticky_false_count += 1
                    missing_sticky_atc_count += 1
                else:
                    sticky_atc_state = "UNKNOWN"
                    sticky_unknown_count += 1

                # Revenue Leak Opportunity
                if "REVENUE_LEAK" in opp_types:
                    revenue_leak_count += 1

                pdp_rows.append({
                    "domain": domain,
                    "url": url,
                    "page_state": page_state,
                    "scanned_variant": scanned_variant,
                    "scanned_variant_id": scanned_variant_id,
                    "oos_state": "TRUE" if out_of_stock else "FALSE",
                    "oos_reason": "OOS verified" if out_of_stock else "Available / Not verified",
                    "bis_state": "TRUE" if notify_button_detected else "FALSE",
                    "review_state": review_state,
                    "upsell_state": upsell_state,
                    "sticky_atc_state": sticky_atc_state,
                    "sold_out_detected": "TRUE" if sold_out_detected else "FALSE",
                    "opportunities": ", ".join(opp_types) if opp_types else "None"
                })

        except Exception as exc:
            errors += 1
            logger.error("Failed processing session file %s: %s", session_file, exc)

    # Compile Markdown content
    md = []
    md.append("# LIVE SAMPLE VALIDATION REPORT")
    md.append(f"**Date compiled:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("\n## Aggregate Metrics")
    md.append(f"- **stores_scanned:** {stores_scanned}")
    md.append(f"- **pdps_scanned:** {pdps_scanned}")
    md.append(f"- **variants_inspected:** {variants_inspected}")
    md.append(f"- **variant_ids_found:** {variant_ids_found}")
    md.append(f"- **oos_true_count:** {oos_true_count}")
    md.append(f"- **bis_true_count:** {bis_true_count}")
    md.append(f"- **review_true_count:** {review_true_count}")
    md.append(f"- **review_false_count:** {review_false_count}")
    md.append(f"- **review_unknown_count:** {review_unknown_count}")
    md.append(f"- **upsell_true_count:** {upsell_true_count}")
    md.append(f"- **upsell_false_count:** {upsell_false_count}")
    md.append(f"- **upsell_unknown_count:** {upsell_unknown_count}")
    md.append(f"- **sticky_true_count:** {sticky_true_count}")
    md.append(f"- **sticky_false_count:** {sticky_false_count}")
    md.append(f"- **sticky_unknown_count:** {sticky_unknown_count}")
    md.append(f"- **revenue_leak_count:** {revenue_leak_count}")
    md.append(f"- **missing_social_proof_count:** {missing_social_proof_count}")
    md.append(f"- **missing_upsell_count:** {missing_upsell_count}")
    md.append(f"- **missing_sticky_atc_count:** {missing_sticky_atc_count}")
    md.append(f"- **screenshots_captured:** {screenshots_captured}")
    md.append(f"- **errors:** {errors}")

    md.append("\n## Per-PDP Details")
    md.append("| Domain | URL | Page State | Scanned Variant | Variant ID | OOS State | BIS State | Review State | Upsell State | Sticky ATC | Sold Out Detected | Opportunities |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in pdp_rows:
        md.append(
            f"| {r['domain']} | {r['url']} | {r['page_state']} | {r['scanned_variant']} | {r['scanned_variant_id']} | "
            f"{r['oos_state']} | {r['bis_state']} | {r['review_state']} | {r['upsell_state']} | {r['sticky_atc_state']} | "
            f"{r['sold_out_detected']} | {r['opportunities']} |"
        )

    # Save to storage/reports
    reports_dir = Path("storage/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "validation_report.md"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    # Print to stdout
    print("\n" + "\n".join(md) + "\n")
    logger.info("Validation report compiled and saved to %s", report_file)

if __name__ == "__main__":
    compile_report()
