# FORENSIC COMMERCIAL & ENGINEERING AUDIT REPORT

**Project:** Revenue Leak Scanner V2  
**Audit Date:** 2026-08-09  
**Auditor:** AntiGravity Forensic Agent  
**Final Status:** **FAIL / NOT PROVEN FOR COMMERCIAL SALE (CLASSIFICATION C)**

---

## EXECUTIVE SUMMARY

A rigorous, line-by-line forensic audit of the Revenue Leak Scanner codebase, test suite, session artifacts, checksums, lead exports, and live-scan outputs was performed.

While the core Playwright browser automation and 3-state detection primitives (`TRUE`, `FALSE`, `UNKNOWN`) are correctly implemented in unit tests and preventing basic crash regressions (117/117 pytest passing), **the current system is NOT READY FOR COMMERCIAL SALE**.

### Critical Commercial & Engineering Vulnerabilities Identified:
1. **Fake Enrichment "SUCCESS" Status ([post_scan_enricher.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/enrichment/post_scan_enricher.py)):**
   - Parses **Product Titles** (e.g., `"Men's Cruiser"`) as **Company Names**.
   - Hardcodes `/pages/contact` URL and lies about provenance by labeling `contact_page_source = "DOM_LINK"`.
   - Returns `"enrichment_status": "SUCCESS"` even when zero emails, zero phones, and zero social links are found.
2. **Hardcoded Summary Reports ([final_lead_validator.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/commercial/final_lead_validator.py)):**
   - The validation generator hardcodes `"Dataset: 39 leads"` and `"FINAL DECISION: READY TO SELL"` directly into string templates regardless of actual audit outcomes.
3. **Aggregator Historical Contamination ([summarize_validation_run.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/summarize_validation_run.py)):**
   - Aggregates all 44 historical folders in `storage/sessions/` instead of isolating the current 10-store run, falsely claiming 44 stores / 127 PDPs scanned.
4. **Current Run Zero OOS / Zero Revenue Leaks:**
   - In the actual current 10-store run (9 successful sessions), **0 out-of-stock variants were found**, resulting in **0 REVENUE_LEAK opportunities**. The current scanner implementation's live variant ID extraction capabilities remain **UNPROVEN ON LIVE DEMAND LEAKS**.

---

## PHASE 0 — INVENTORY & ARCHITECTURE MAP

### Project Inventory Summary:
- **Source Files (35):** Core scanner, CRO detectors, evidence collectors, lead exporters, impact calculators, post-scan enricher.
- **Test Files (11):** 117 unit/integration tests in `tests/`.
- **Session Bundles (44):** Directories under `storage/sessions/` (9 current run + 35 historical legacy).
- **Export Artifacts:** [leads.json](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/storage/leads/leads.json), [leads.csv](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/storage/leads/leads.csv), [validation_report.md](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/storage/reports/validation_report.md), [live_run_summary.json](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/live_run_summary.json).

### Architecture Flow Map:
```
[Discovery (product_discovery.py)]
    ↓ Validated Product URLs
[PDP Validation (page_validator.py)]
    ↓ Real PDP verified (PAGE_STATE == REAL_PRODUCT)
[Variant / OOS Engine (variant_matrix.py)]
    ↓ Layer 0 JS / Layer 1 CSS / Layer 2 Selectors
[BIS Modal Checker (bis_checker.py)]
    ↓ BIS Modal Absence/Presence
[CRO Stack Detector (cro_stack_detector.py)]
    ↓ 3-State (TRUE/FALSE/UNKNOWN) for Reviews, Upsells, Sticky ATC
[Opportunity Gate (core_scanner.py)]
    ↓ Strict Verification Gates (OOS+ID+NoBIS or Confirmed CRO Absence)
[Evidence Collector & Serializer (evidence_collector.py, session_serializer.py)]
    ↓ Canonical JSON, Screenshots, Checksums
[Confidence Engine (evidence_scorer.py)]
    ↓ Dynamic Lead Scoring & Penalty Deduction
[Financial Impact (impact_calculator.py)]
    ↓ Measured vs Fallback Benchmark Scenario Calculation
[Lead Classification & Enrichment (post_scan_enricher.py, lead_exporter.py)]
    ↓ Class A/B/C Sorting & Metadata Post-Processing
[Lead Export & Reporting (lead_exporter.py, summarize_validation_run.py)]
    ↓ JSON/CSV Leads & Audit PDF/Teasers
```

---

## PHASE 1 — CONTRACT AUDIT MATRIX

| CONTRACT / INVARIANT | IMPLEMENTATION LOCATION | TEST COVERAGE | LIVE PROOF | STATUS | RISK LEVEL |
|---|---|---|---|---|---|
| **PDP Validity Gate** | [page_validator.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/scanner/page_validator.py#L45-L95) | [test_pdp_validation.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/tests/test_pdp_validation.py) | Verified on non-product pages | **PASS** | LOW |
| **3-State Strictness (UNKNOWN → 0 opps)** | [core_scanner.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/scanner/core_scanner.py#L140-L175) | [test_live_regression_fixes.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/tests/test_live_regression_fixes.py) | Verified on 19 UNKNOWN review PDPs | **PASS** | LOW |
| **OOS Variant Identity (`scanned_variant_id != ""`)** | [core_scanner.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/scanner/core_scanner.py#L122) | [test_scanner.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/tests/test_scanner.py) | UNPROVEN in current live run (0 OOS found) | **NOT PROVEN** | **HIGH** |
| **1:1 Evidence Screenshot Binding** | [evidence_collector.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/evidence/evidence_collector.py) | [test_evidence.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/tests/test_evidence.py) | Verified across 9 current sessions | **PASS** | LOW |
| **Enrichment Provenance & Authenticity** | [post_scan_enricher.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/enrichment/post_scan_enricher.py#L110-L130) | [test_post_scan_enricher.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/tests/test_post_scan_enricher.py) | **FAILS**: Uses product titles as company names & hardcodes contact URLs | **FAIL** | **CRITICAL** |
| **Report Isolation (Current Run Only)** | [summarize_validation_run.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/summarize_validation_run.py#L40-L60) | None | **FAILS**: Aggregates 35 historical folders | **FAIL** | **CRITICAL** |
| **Lead Validation Report Generation** | [final_lead_validator.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/commercial/final_lead_validator.py#L170-L191) | None | **FAILS**: Hardcodes dataset count and decision text | **FAIL** | **CRITICAL** |

---

## PHASE 2 — PDP VALIDATION FORENSICS

- **Non-Product Boundaries:** Collection, blog, cart, checkout, account, search, and malformed URLs are evaluated by [PageValidator](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/scanner/page_validator.py).
- **Execution Rule:** If `page_state != PageState.REAL_PRODUCT`, `core_scanner.py` returns 0 opportunities.
- **Verification:** Unit tests confirm 404, collection, and non-product pages return zero commercial opportunities.

---

## PHASE 3 & 4 — VARIANT / OOS & REVENUE LEAK GATE FORENSICS

### Execution Trace of `discover_oos_variant_state()`:
1. **Layer 0 (JS-based):** Evaluates `_JS_VARIANT_EXTRACTION_SCRIPT` against `window.ShopifyAnalytics.meta.product.variants`, `window.Shopify.product.variants`, `window.meta.product.variants`, or inline `script[type="application/json"]`.
2. **Layer 1 (CSS Heuristics):** Checks input radios, swatches, option buttons for `disabled` state or `sold-out` classes.
3. **Layer 2 (Select Fallback):** Checks `<select>` dropdown `<option>` elements for `disabled` or sold-out text.

### Current Run Verdict:
In the current 10-store live run (9 successful sessions), **all inspected variants across all 26 PDPs were available in stock**.
- `out_of_stock == False` for 26/26 PDPs.
- `scanned_variant_id == ""` for 26/26 PDPs.
- **Current Live REVENUE_LEAK opportunities:** 0.

---

## PHASE 5 — CRO ENGINES FORENSICS

### Detector State Breakdown (Current 9 Live Sessions / 26 PDPs):
- **Social Proof Reviews:** 7 `TRUE` (Present), 0 `FALSE`, 19 `UNKNOWN`. Opportunities generated: **0**.
- **Upsells:** 1 `TRUE` (Present), 0 `FALSE`, 25 `UNKNOWN`. Opportunities generated: **0**.
- **Sticky ATC:** 0 `TRUE`, 13 `FALSE` (Confirmed Absent on >1200px scrollable pages), 13 `UNKNOWN`. Opportunities generated: **13 `MISSING_STICKY_ATC`**.

*Invariant Check:* Zero opportunities were generated from `UNKNOWN` detector states.

---

## PHASE 6 & 7 — EVIDENCE & CHECKSUM FORENSICS

- All 9 current session directories in `storage/sessions/` contain `.json`, `.png`, and `.checksum` files.
- SHA-256 calculation verified 100% hash parity between disk PNGs and `.checksum` files.
- 1:1 binding verified: Each finding maps directly to its session screenshot without cross-contamination.

---

## PHASE 8 TO 13 — COMMERCIAL ENGINE FORENSICS

### 1. Enrichment Defects ([post_scan_enricher.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/enrichment/post_scan_enricher.py)):
- **Product Title as Company Name:** Takes `finding.product_name` (e.g. `"Men's Cruiser"`) and sets `company_name = "Men's Cruiser"`.
- **False Provenance:** Hardcodes `contact_page = base_url + "/pages/contact"` and sets `contact_page_source = "DOM_LINK"` even when no link was extracted from DOM.
- **Fake Success:** Sets `enrichment_status = "SUCCESS"` whenever `company_name` (product title) and `contact_page` (hardcoded path) are present, even with 0 emails, phones, or social handles.

### 2. Lead Export Integrity ([leads.json](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/storage/leads/leads.json)):
- Contains historical lead records from previous test runs mixed with current data.
- Lead company names show product names (`"Men's Cruiser"`, `"The Fired Ups"`).

---

## PHASE 14 — AGGREGATOR FORENSICS

- `summarize_validation_run.py` iterates recursively over all 44 folders in `storage/sessions/`.
- Falsely reports 44 stores / 127 PDPs / 3 Revenue Leaks as the output of the current run, when 35 of those folders are historical legacy scans.

---

## PHASE 17 — ADVERSARIAL TESTING MATRIX (KEY SCENARIOS)

| SCENARIO | EXPECTED BEHAVIOR | ACTUAL BEHAVIOR | PASS / FAIL | RISK |
|---|---|---|---|---|
| **OOS Variant + Empty Variant ID** | Gate Rejection (0 opps) | Gate Rejection (0 opps) | **PASS** | LOW |
| **OOS Variant + Valid Variant ID + No BIS** | Creates `REVENUE_LEAK` | Creates `REVENUE_LEAK` (in unit tests) | **PASS (Mock)** | LOW |
| **UNKNOWN Review State** | 0 Social Proof Opps | 0 Social Proof Opps | **PASS** | LOW |
| **Short Page (<1200px) Sticky ATC Check** | Returns `UNKNOWN` | Returns `UNKNOWN` | **PASS** | LOW |
| **Post-Scan Enrichment on Domain** | Extracts Store Brand & REAL Contact Data | Uses Product Title as Brand Name & Hardcodes `/pages/contact` | **FAIL** | **CRITICAL** |
| **Validation Report Compilation** | Summarizes Current Run Only | Aggregates 35 Historical Directories | **FAIL** | **CRITICAL** |
| **Lead Validation Markdown Generation** | Dynamic Metric Export | Hardcodes `"Dataset: 39 leads"` & `"READY TO SELL"` | **FAIL** | **CRITICAL** |

---

## PHASE 18 — COMMERCIAL BUYER SIMULATION

### Buyer Trust Score: **35 / 100**

#### Why a Buyer Would Reject Current Output:
1. **Wrong Company Name:** Cold emails generated from `leads.json` will address store owners as "Dear Men's Cruiser" or "Dear The Fired Ups" instead of "Dear Allbirds" or "Dear Chubbies Shorts".
2. **Missing Contact Data:** Email and phone fields are `null` for most leads; `contact_page` is hardcoded to `/pages/contact` without checking if that page returns 200 OK or 404.
3. **Contaminated Aggregation:** Reports state 44 stores scanned when only 10 were targeted.

---

## PHASE 19 — UNDISCOVERED BUGS & ENGINEERING DEFECTS

1. **Company Name Extraction Fallback:** Missing domain-based fallback (e.g. `domain.split('.')[0].capitalize()`) when product title is used.
2. **Contact Page Provenance Illusion:** Hardcoded `urljoin(base_url, "/pages/contact")` claims `DOM_LINK` source.
3. **Hardcoded Summary Templates:** `final_lead_validator.py` writes static text metrics instead of computed counters.
4. **Aggregator Scope Unbounded:** `summarize_validation_run.py` lacks run ID or timestamp isolation.

---

## PHASE 20 — FINAL VERDICT & ACTION PLAN

### FINAL CLASSIFICATION: **CLASSIFICATION C — FAILED / NOT READY FOR SALE**

---

### What is Definitely Fixed:
- 117 unit/integration tests passing cleanly.
- Strict 3-state CRO detection primitives (`TRUE`, `FALSE`, `UNKNOWN`).
- 1:1 Screenshot evidence collector and SHA-256 checksum verification.
- Real PDP validation boundaries.

### What is Definitely Broken:
1. [post_scan_enricher.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/enrichment/post_scan_enricher.py): Parses product title as company name; hardcodes contact page URL & lies about DOM provenance; sets fake `"SUCCESS"` status.
2. [summarize_validation_run.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/summarize_validation_run.py): Contaminates reports with historical sessions.
3. [final_lead_validator.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/commercial/final_lead_validator.py): Hardcodes report text strings (`"Dataset: 39 leads"`).

---

### Exact Files That Must Change:
1. [src/enrichment/post_scan_enricher.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/enrichment/post_scan_enricher.py)
2. [summarize_validation_run.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/summarize_validation_run.py)
3. [src/commercial/final_lead_validator.py](file:///C:/Users/Admin/Downloads/revenue_leak_scanner/RevenueLeakScanner_V2/src/commercial/final_lead_validator.py)

---

### Final Decision: **NO-GO FOR COMMERCIAL SALE UNTIL ENRICHMENT AND REPORTING DEFECTS ARE RESOLVED.**
