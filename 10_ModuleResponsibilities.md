# 10 Module Responsibilities & System Locks — Revenue Leak Scanner V2

## 1. Executive Summary & Design Lock Purpose

This document seals the **5 Design Locks** required before any Phase A code implementation begins. It specifies the mathematical algorithms, data contract bounds, physical storage invariants on Windows OS, and single-responsibility interfaces for every package in Version 2.

```
+-----------------------------------------------------------------------------------+
|                            THE FIVE DESIGN LOCKS (PRE-CODE)                       |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  LOCK 1: Revenue Loss Mathematical Formula & Data Source Specification            |
|  LOCK 2: OOS Frequency Ratio Mathematical Definition                             |
|  LOCK 3: Multi-Finding Session Bundle Hierarchy                                   |
|  LOCK 4: Canonical JSON Serialization & Checksum Hashing Algorithm                |
|  LOCK 5: Windows OS Architectural Immutability Enforcement                        |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 2. THE FIVE ARCHITECTURAL DESIGN LOCKS

### LOCK 1: Lost Revenue Estimation Formula & Source Matrix

To prevent misleading claims, every financial estimate MUST disclose its confidence score and data sources:

$$\text{Est. Monthly Lost Revenue (\$)} = \text{Monthly Traffic} \times \text{OOS Ratio} \times \text{Baseline CR} \times \text{AOV}$$

```
+-----------------------------------------------------------------------------------+
|                           PARAMETER SOURCE & CONFIDENCE MATRIX                    |
+-----------------------------------------------------------------------------------+
```

| Formula Parameter | Primary Data Source | Fallback Mechanism | Confidence Impact |
|---|---|---|---|
| **Monthly Traffic** | Tranco / BuiltWith API estimation bucket | Category Median Tier (e.g. 50,000 visits/mo) | Drops `confidence_score` by `-0.3` if fallback used. |
| **OOS Ratio** | Scraped OOS variants / Scanned variants | Minimum 5.0% cap | Calculated directly from live scan findings. |
| **Baseline CR** | E-Commerce Category Benchmark (Default: 2.0%) | Static 2.0% Constant | Explicitly disclosed in report footnotes as benchmark. |
| **AOV (Average Order Value)** | Extracted PDP product price | Category Median AOV ($65.00) | Extracted directly from DOM price tag. |

* **Disclosure Rule:** If any parameter uses a fallback mechanism, the final `CommercialImpact` object MUST set `confidence_score < 0.70` and display an explicit footnote disclosing estimated parameters.

---

### LOCK 2: `oos_frequency_pct` Mathematical Definition

* **Definition:** `oos_frequency_pct` is strictly defined as the ratio of **scanned unavailable variants to total scanned variants** across inspected PDPs during the session.

$$\text{OOS Frequency (\%)} = \left( \frac{\text{Count of Out-Of-Stock Variants Selected}}{\text{Total Variants Inspected across Scanned PDPs}} \right) \times 100$$

* **Catalog Scope:** It represents the **Inspected Sample Density**, NOT the total un-scanned store catalog. The JSON payload must explicitly document `variants_inspected` and `variants_oos`.

---

### LOCK 3: Multi-Finding Session Bundle Hierarchy

A single `SessionBundle` represents a **Full Store Audit Session**, which may contain multiple individual PDP leak findings:

```
SessionBundle (1 Store Audit Session)
    │
    ├── StoreMetadata & CommercialSummary
    │
    └── Findings (List of Individual Leak Finding Objects)
         │
         ├── Finding 1 (PDP A: e.g. TOMS Santiago Loafer) ──► VisualEvidence + BoundingBoxes
         ├── Finding 2 (PDP B: e.g. TOMS Alpargata Shoe)   ──► VisualEvidence + BoundingBoxes
         └── Finding N (PDP N)                            ──► VisualEvidence + BoundingBoxes
```

* **Scalability Guarantee:** Downstream drivers (PDF, HTML, Teaser) can render single-finding teasers (`Finding 1`) OR multi-finding audit decks (`Finding 1..N`) from the exact same `SessionBundle`.

---

### LOCK 4: Canonical Serialization & Checksum Algorithm

To guarantee identical SHA-256 hashes across different OS platforms and Python runtimes, JSON serialization MUST follow strict **Canonical JSON Rules**:

```
+-----------------------------------------------------------------------------------+
|                        CANONICAL JSON SERIALIZATION RULES                         |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. Key Sorting:        sort_keys = True (Alphabetical lexicographical order)    |
|  2. Compact Whitespace: separators = (',', ':') (Zero indentations or spaces)     |
|  3. Character Encoding: ensure_ascii = False, encoding = 'utf-8'                  |
|  4. Float Formatting:   Floats rounded to 4 decimal places (e.g. 12.3456)         |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

#### Deterministic Checksum Hash Calculation:
$$\text{Checksum} = \text{SHA256} \left( \text{SHA256}(\text{PNG Bytes}) + \text{SHA256}(\text{Canonical JSON UTF-8 Bytes}) \right)$$

---

### LOCK 5: Windows OS Architectural Immutability Enforcement

Because Windows OS file permissions (`win32file.SetFileAttributes`) can be bypassed or toggled by background processes, immutability MUST be enforced at the **System Architecture Level**:

1. **Write-Once Storage Manager:** `session_serializer.py` raises `SessionExistsException` if an attempt is made to serialize a `session_id` that already exists on disk.
2. **Read-Only File Handler:** Output Drivers load session bundles using read-only Python file handlers (`open(path, 'r', encoding='utf-8')`).
3. **No Overwrite APIs:** The `SessionStorage` interface provides `save_new_bundle()` and `get_bundle()`. It contains **NO `update_bundle()` or `overwrite_bundle()` methods.**
4. **Windows File Attribute Lock:** Post-writing, `os.chmod(path, stat.S_IREAD)` is executed as an additional OS-level safeguard.

---

## 3. PACKAGE & MODULE RESPONSIBILITY MATRIX (SRP)

Below is the single-responsibility matrix for all packages in `src/`:

```
+-----------------------------------------------------------------------------------+
|                        MODULE RESPONSIBILITY MATRIX (SRP)                         |
+-----------------------------------------------------------------------------------+
```

| Package / Module | Encapsulated Single Responsibility | Banned Operations |
|---|---|---|
| `src/ingestion/store_loader.py` | Ingests CSV/JSON target store records and validates RFC URL formats. | Banned from making Playwright or HTTP requests. |
| `src/ingestion/tenant_config.py` | Loads agency white-label branding (logos, colors, booking links). | Banned from importing scanner logic. |
| `src/scanner/browser_factory.py` | Initializes process-isolated Playwright browser instances and contexts. | Banned from inspecting DOM elements. |
| `src/scanner/core_scanner.py` | Orchestrates PDP navigation and drives DOM scraper sub-modules. | Banned from rendering outputs or editing sidecars. |
| `src/scanner/variant_matrix.py` | Discovers and clicks unavailable variant option pills in the DOM. | Banned from taking screenshots or writing JSON. |
| `src/scanner/bis_checker.py` | Inspects DOM and network requests for Back-in-Stock capture modals. | Banned from calculating financial loss metrics. |
| `src/commercial/impact_calculator.py`| Computes lost revenue dollars ($/mo), lead priority, and confidence scores. | Banned from modifying DOM or taking screenshots. |
| `src/evidence/evidence_collector.py`| Drives page scrolling, overlay suppression, and screenshot capture. | Banned from scoring or ranking evidence candidates. |
| `src/evidence/visual_verifier.py` | Asserts screenshot Pillow stream integrity and blank canvas extrema. | Banned from modifying image pixels. |
| `src/evidence/session_serializer.py`| Compiles `SessionBundle`, calculates checksum, and enforces write-once disk storage. | Banned from overwriting existing session IDs. |
| `src/selection/candidate_selector.py`| Globs session bundles, evaluates ground-truth assertions, and selects highest scorer. | Banned from mutating session files on disk. |
| `src/presentation/payload_compiler.py`| Compiles driver-specific DTOs (`PDFPayload`, `EmailPayload`, `DashboardPayload`). | Banned from hardcoding brand names or URLs. |
| `src/presentation/drivers/pdf_driver.py`| Renders 1-Page Executive PDFs (`audit.pdf`) via template engine. | Banned from executing Playwright or calling scanner API. |
| `src/presentation/drivers/teaser_driver.py`| Generates cropped cold outreach email teaser images (`teaser.png`). | Banned from modifying source PNG files. |

---

## 4. ARCHITECTURAL DECISION RECORDS (ADRs)

### ADR-MR-001: Sealing the Five Design Locks
* **Status:** Accepted
* **Context:** Ambiguity in financial formulas, OOS frequency ratios, or checksum algorithms could cause developer interpretations to diverge during Phase A implementation.
* **Decision:** The Five Design Locks in `10_ModuleResponsibilities.md` are sealed as binding architectural specifications.
* **Consequences:** Implementation code in Phase A through Phase G must conform to these locks without alteration.

### ADR-MR-002: Architectural Immutability on Windows OS
* **Status:** Accepted
* **Context:** Reliance on OS-level file attributes alone is insufficient on Windows environments.
* **Decision:** Immutability is enforced architecturally via Write-Once Storage APIs (`save_new_bundle`) lacking overwrite functions.
* **Consequences:** Attempting to save a duplicate session ID raises an immutable system exception.
