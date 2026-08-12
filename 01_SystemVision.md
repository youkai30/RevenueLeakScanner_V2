# 01 System Vision — Revenue Leak Scanner V2

## 1. Executive Summary & Vision Statement

Revenue Leak Scanner V2 is an enterprise-grade, automated B2B revenue intelligence platform designed specifically for Shopify CRO (Conversion Rate Optimization) and E-commerce Growth Agencies.

```
+-----------------------------------------------------------------------------------+
|                               SYSTEM VISION STATEMENT                             |
+-----------------------------------------------------------------------------------+
|  "To provide CRO agencies with unassailable, visually verified, and dollar-       |
|   quantified proof of lost e-commerce revenue—transforming cold prospect         |
|   outreach into high-converting, trust-anchored sales conversations."             |
+-----------------------------------------------------------------------------------+
```

Version 2 represents a complete architectural redesign from a developer diagnostic script into a commercial-first B2B Lead Generation and Audit Platform. It replaces fragile scraping heuristics, hardcoded presentation layers, and un-scoped evidence pools with a deterministic, session-isolated, and single-source-of-truth system architecture.

---

## 2. Non-Goals (Scope Boundary Laws)

To prevent feature creep and maintain strict architectural focus, **Revenue Leak Scanner V2 is explicitly NOT:**

* **NOT a Shopify App / Theme Extension:** It operates strictly external to client store infrastructure via automated browser inspection.
* **NOT an SEO / Performance Auditor:** It ignores Lighthouse scores, page speed, broken links, and metadata tags unrelated to conversion leaks.
* **NOT a Marketing Automation Platform:** It does not send cold outreach emails or manage agency CRM pipelines natively.
* **NOT a Generic Web Scraper:** It does not extract arbitrary HTML data; it inspects specific conversion funnel mechanics (out-of-stock SKUs & restock alerts).
* **NOT a BI Dashboard / Analytics Suite:** It does not integrate with Google Analytics or Shopify Admin APIs for historical store metrics.

---

## 3. Design Philosophy

The architecture of Version 2 prioritizes foundational system guarantees over short-term implementation shortcuts:

```
+-----------------------------------------------------------------------------------+
|                              SYSTEM DESIGN PHILOSOPHY                             |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. Determinism over Convenience                                                  |
|  2. Verified Evidence over Heuristics & Guesswork                                |
|  3. System Verification over Assumptions                                          |
|  4. Strict Architecture over Quick Feature Addition                               |
|  5. Commercial Value over Technical Elegance                                       |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 4. Architectural Governing Principles

All future code design and module creation within Version 2 must strictly comply with these core laws:

1. **One Data Owner:** Every single data attribute (URL, price, review count, bounding box) has exactly ONE designated module owner authorized to write it.
2. **One Responsibility Per Module:** Strict single-responsibility encapsulation across scanner, capture, selection, and rendering modules.
3. **No Hidden State:** Global variables, untracked transient dictionaries, and implicit side-channel data passes are banned.
4. **No Runtime Mutation:** Once a `SessionBundle` is written to disk, its content is strictly immutable.
5. **No Duplicate Pipelines:** Production and Demo modes execute through identical scanner and presentation code paths.
6. **Immutable Evidence:** Screenshots and their spatial metadata are deterministically bound at the millisecond of capture.
7. **Deterministic Outputs:** Identical input datasets under identical DOM conditions MUST produce identical report structures.
8. **Configuration over Hardcoding:** Presentation templates, styling tokens, and rule thresholds live in explicit configuration files, never in Python execution logic.

---

## 5. Core Architectural Pillars

```
+-----------------------------------------------------------------------------------+
|                              CORE ARCHITECTURAL PILLARS                           |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. ATOMIC EVIDENCE INTEGRITY                                                     |
|     Every visual proof artifact is deterministically bound to its runtime DOM     |
|     state in a single, immutable Session Bundle. Zero cross-session leakage.      |
|                                                                                   |
|  2. SINGLE SOURCE OF TRUTH (SSOT)                                                 |
|     100% of presentation data, metrics, and visual callouts are rendered from     |
|     the Session Bundle. Zero hardcoded presentation arrays in code.               |
|                                                                                   |
|  3. UNIFIED PIPELINE PARITY                                                       |
|     Production scans and Commercial Demo builds run through identical scanner,    |
|     validation, and rendering pipelines. Zero out-of-band file mutators.          |
|                                                                                   |
|  4. COMMERCIAL-FIRST ENGINE                                                       |
|     Built to output dollar-quantified loss estimates ($/month), single-store      |
|     executive PDFs, and 1-click cold email image teasers for SDR teams.            |
|                                                                                   |
|  5. ENTERPRISE SAAS SCALABILITY                                                   |
|     Process-isolated worker pools, white-label tenant support, and multi-format   |
|     export readiness (PDF, HTML, JSON API, Dashboard).                            |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 6. Definition of a Session Bundle

A **Session Bundle** is the single deployable and immutable evidence artifact produced by a scan run. It represents the complete state of a store audit at the millisecond of capture.

```
+-----------------------------------------------------------------------------------+
|                             SESSION BUNDLE CONTENTS                               |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. Session ID               (UUIDv4 unique session identifier)                   |
|  2. Store Metadata           (Domain, Industry, Scanned PDP URL, Timestamp)       |
|  3. Scanner Findings         (Out-of-Stock Status, Notify Button State)           |
|  4. Commercial Metrics       (Estimated Monthly Lost Revenue $, Lead Priority)    |
|  5. Bounding Boxes           (Spatial Coordinates: x, y, width, height)            |
|  6. Visual Evidence          (Verified PNG Screenshot File Path)                  |
|  7. Evidence Hash            (SHA-256 Checksum of PNG & Metadata payload)         |
|  8. Presentation Payload     (Narrative Copy, Callout Tags, Agency Sales Angle)   |
|  9. Validation State         (Visual Integrity & Rule Assertion Verification)     |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 7. High-Level System Context (C4 Context Diagram)

```
                                      +-----------------------------------+
                                      |          Agency SDR / AE          |
                                      +-----------------------------------+
                                                        │
                                                        │ Uses Prospecting Tool
                                                        ▼
+-----------------------+             +-----------------------------------+             +-----------------------+
|  Shopify E-Commerce   |             |   Revenue Leak Scanner V2 Engine  |             |  Brand Decision Maker |
|  Target Store PDP     | ──Scrapes──►|  (Process Workers / Evidence API) | ──Outputs──►|  (Shopify Founder/CMO)|
+-----------------------+             +-----------------------------------+             +-----------------------+
                                                        │
                                                        │ Generates Pitch Assets
                                                        ▼
                                      +-----------------------------------+
                                      | 1. Cropped Outreach Image Teasers |
                                      | 2. Executive Audit PDFs (1-Page)  |
                                      | 3. Multi-Store Benchmark Decks    |
                                      +-----------------------------------+
```

---

## 8. Definition of System Success

Revenue Leak Scanner V2 is considered successfully architected and implemented when:

1. **Zero Hardcoded Presentation Data:** 100% of titles, copy, URLs, and callouts render from the `SessionBundle`.
2. **One Unified Pipeline:** Demo builds execute through the production scanner/validator engine using pre-seeded fixtures.
3. **Strict Session Isolation:** Every screenshot and metadata sidecar is scoped inside a unique `session_<uuid>` directory.
4. **Single Source of Truth:** Zero presentation fields exist in python code constants.
5. **One Data Owner Per Field:** Every JSON attribute has an explicit, un-shared owner class.
6. **Reproducible Reports:** Running the report builder against the same `SessionBundle` produces bit-for-bit identical outputs.
7. **Automated Commercial Assets:** Single-store executive PDFs and cold outreach image teasers generate automatically.

---

## 9. Architecture Decision Records (ADRs)

### ADR-001: Session Bundle Immutability
* **Status:** Accepted
* **Context:** Legacy V1 allowed file copiers to overwrite `.meta.json` sidecars post-capture, causing visual text mismatches.
* **Decision:** All scan evidence must be saved as a `SessionBundle`. Once serialized to disk, a `SessionBundle` is strictly read-only and sealed with a SHA-256 checksum.
* **Consequences:** Modifying demo data requires re-running fixture scans through the engine rather than editing disk files manually.

### ADR-002: Demo Mode Pipeline Parity
* **Status:** Accepted
* **Context:** V1 used a dedicated `prepare_demo_sidecars.py` copier script that bypassed scanner validation logic entirely.
* **Decision:** Demo mode must execute through the primary Production Scanner engine using pre-recorded network fixtures.
* **Consequences:** Guarantees that any bug or validation failure present in production will be caught immediately in demo builds.

### ADR-003: Presentation Payload Co-Location in Session Bundle
* **Status:** Accepted
* **Context:** V1 split data between disk sidecars and the `SAMPLE_STORES` array in `generate_opportunity_report.py`.
* **Decision:** 100% of report presentation text, labels, and strategic narratives belong to the `SessionBundle` presentation payload.
* **Consequences:** `generate_opportunity_report.py` becomes a pure template renderer with zero knowledge of specific brand names or URLs.

---

## 10. Key Architectural Transformations (V1 vs. V2)

| Architectural Dimension | Version 1 (Legacy Infrastructure) | Version 2 (Redesigned Platform) |
|---|---|---|
| **Data Ownership** | Fragmented across `SAMPLE_STORES` (in-memory) and `.meta.json` (disk). | **Single Source of Truth**: 100% stored inside immutable `SessionBundle`. |
| **Evidence Scoping** | Directory-level globbing (`*.meta.json`) across all time. | **Strict UUID Session Isolation**: `screenshots/<domain>/<session_id>/`. |
| **Demo Pipeline** | Out-of-band copier (`prepare_demo_sidecars.py`) overwriting disk files. | **Unified Pipeline Parity**: Fixture-driven execution through identical scanner paths. |
| **Commercial Metric** | Qualitative badges (`Revenue Leak — High`). | **Quantified Impact**: Financial formula ($/month lost revenue calculation). |
| **Deliverable Format** | Single 7MB multi-store HTML file (`FREE_SAMPLE_10_STORES.html`). | **Multi-Format Export Engine**: Single-store PDF, Email Teaser Image, & Interactive HTML. |
| **Presentation Layer** | Hardcoded titles, copy, and URL dictionaries in renderer python code. | **Zero Code Presentation Data**: All copy and annotations dynamically compiled into session payload. |
| **Visual Verification** | Unverified DOM selector extraction. | **Visual Verification Gate**: Automated Pillow/OCR assertion matching rendered pixels to facts. |
| **Evidence Binding** | Loose filename matching. | **Deterministic Checksum**: SHA-256 checksum binding PNG bytes to JSON payload. |
