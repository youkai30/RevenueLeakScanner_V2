# 06 Data Model — Revenue Leak Scanner V2

## 1. Executive Summary & Data Model Philosophy

The Data Model of Revenue Leak Scanner V2 defines every core entity, object structure, relationship, and validation boundary in the system.

```
+-----------------------------------------------------------------------------------+
|                             DATA MODEL GOVERNING LAW                              |
+-----------------------------------------------------------------------------------+
|  "Every data object in V2 must be strongly typed, immutably serializable,         |
|   have exactly ONE explicit Owner class, and enforce its own validation rules     |
|   at instantiation time."                                                         |
+-----------------------------------------------------------------------------------+
```

### Core Architectural Shift: Output Drivers vs. Scanner Goal
The system architecture treats the **Scanner Engine as an Evidence Generator**, NOT a report builder. The final report is merely one of many **Output Drivers** (alongside PDF, Email Teasers, CRM Webhooks, and API Payloads) consuming an immutable `SessionBundle`.

```
[Target Store] ──► [Scanner Engine] ──► [ScanContext (Transient)] ──► [SessionBundle (Immutable)]
                                                                               │
       ┌─────────────────────────┬─────────────────────────┬───────────────────┴─────────────────────┐
       ▼                         ▼                         ▼                                         ▼
[PDF Driver]              [Teaser Driver]          [Dashboard Driver]                         [CRM / API Driver]
(audit.pdf)               (teaser.png)             (JSON API)                                 (Webhook Payload)
```

---

## 2. Entity Relationship Diagram (ERD)

```
+------------------+         1 : N         +------------------+
|   StoreRecord    | --------------------> |  SessionBundle   |
+------------------+                       +------------------+
| - domain         |                       | - session_id     |
| - base_url       |                       | - build_id       |
| - industry       |                       | - schema_version |
+------------------+                       | - scanner_version|
                                           +------------------+
                                                    │
                         ┌──────────────────────────┼──────────────────────────┐
                         │ 1 : 1                    │ 1 : 1                    │ 1 : 1
                         ▼                          ▼                          ▼
               +------------------+       +------------------+       +------------------+
               | VisualEvidence   |       | CommercialImpact |       | BoundingBoxMap   |
               +------------------+       +------------------+       +------------------+
               | - png_file_path  |       | - est_loss_usd   |       | - buy_box        |
               | - sha256_hash    |       | - lead_priority  |       | - cta / notify   |
               | - capture_ms     |       | - traffic_bucket |       | - price / review |
               | - viewport       |       +------------------+       +------------------+
               +------------------+
```

---

## 3. Comprehensive Domain Entity Inventory

Below is the complete specification for all core domain objects in Version 2:

### 1. `StoreRecord`
* **Purpose:** Represents an incoming e-commerce store target to be audited.
* **Fields:** `domain` (str), `base_url` (str), `industry` (str), `country` (str), `created_at` (datetime).
* **Single Owner:** `src/ingestion/store_loader.py`
* **Lifecycle:** Instantiated at ingestion ➔ Read by scanner ➔ Retained in process memory.
* **Validation Rules:** `domain` must be a valid RFC-compliant hostname; `base_url` must start with `http://` or `https://`.

### 2. `ScanContext` (TRANSIENT RUNTIME STATE — NOT PERSISTED)
* **Purpose:** Transient, in-memory execution workspace used by Playwright scanner modules during active page inspection.
* **Fields:** `product_name` (str), `product_url` (str), `scanned_variant` (str), `out_of_stock` (bool), `notify_button_detected` (bool), `sold_out_detected` (bool), `review_widget_detected` (bool), `review_platform` (str), `review_count` (int).
* **Single Owner:** `src/scanner/core_scanner.py`
* **Lifecycle:** Instantiated at page load ➔ Updated during DOM discovery ➔ Passed to `EvidenceBuilder` ➔ **Destroyed (Garbage Collected)**. Does NOT enter `SessionBundle`.
* **Validation Rules:** `review_count` $\ge 0$; `product_url` must belong to target domain.

### 3. `SessionBundle` (IMMUTABLE EVIDENCE ARTIFACT)
* **Purpose:** The single deployable, immutable, and sealed evidence artifact representing a completed audit run.
* **Fields:** 
  * `session_id` (UUIDv4), `build_id` (UUIDv4 / Batch ID), `schema_version` (str: `"2.0.0"`), `scanner_version` (str: `"2.3.1"`).
  * `domain` (str), `timestamp` (ISO-8601).
  * `evidence` (VisualEvidence), `commercial` (CommercialImpact), `boxes` (BoundingBoxMap), `checksum` (str: SHA-256).
* **Single Owner:** `src/evidence/session_serializer.py`
* **Lifecycle:** Constructed by `EvidenceBuilder` ➔ Serialized to disk ➔ Read-only permanently.
* **Validation Rules:** `schema_version == "2.0.0"`; `checksum` must match SHA-256 hash of PNG bytes + JSON payload.

### 4. `VisualEvidence`
* **Purpose:** Binds the physical screenshot asset to its quality validation and runtime environment metadata.
* **Fields:** `image_path` (str), `relative_path` (str), `width` (int), `height` (int), `sha256_hash` (str), `capture_duration_ms` (int), `browser_version` (str), `viewport` (str: `"1365x900"`), `valid` (bool), `validation_reason` (str).
* **Single Owner:** `src/evidence/visual_verifier.py`
* **Lifecycle:** Created post-capture ➔ pillow verified ➔ Hashed ➔ Stored in `SessionBundle`.
* **Validation Rules:** `width` $\ge 1024$, `height` $\ge 600$, `capture_duration_ms > 0`.

### 5. `BoundingBox` & `BoundingBoxMap`
* **Purpose:** Represents exact DOM spatial coordinates for callout tag placement.
* **Fields (`BoundingBox`):** `x` (float), `y` (float), `width` (float), `height` (float).  
* **Fields (`BoundingBoxMap`):** `buy_box` (BoundingBox|None), `cta` (BoundingBox|None), `notify` (BoundingBox|None), `reviews` (BoundingBox|None), `upsell` (BoundingBox|None), `sticky_atc` (BoundingBox|None).
* **Single Owner:** `src/evidence/bounding_box_extractor.py`
* **Lifecycle:** Extracted from DOM ➔ Checked for non-zero dimensions ➔ Stored in `SessionBundle`.
* **Validation Rules:** `x, y, width, height` must be non-negative.

### 6. `CommercialImpact` (PURE DOMAIN DATA)
* **Purpose:** Holds calculated financial loss metrics and agency outreach priority ratings. Stripped of business strategy / sales angle.
* **Fields:** `est_monthly_traffic` (int), `oos_frequency_pct` (float), `est_monthly_loss_usd` (float), `lead_priority` (str: HIGH/MED/LOW), `confidence_score` (float: 0.0 to 1.0).
* **Single Owner:** `src/commercial/impact_calculator.py`
* **Lifecycle:** Calculated post-scan ➔ Injected into `SessionBundle`.
* **Validation Rules:** `est_monthly_loss_usd` $\ge 0.0$; `confidence_score` between `0.0` and `1.0`.

### 7. Multi-Format Presentation Payloads (`src/presentation/payloads/`)
Presentation payloads are constructed dynamically by `PresentationCompiler` per output driver.

```
                                  +------------------------------------+
                                  |        PresentationCompiler        |
                                  +------------------------------------+
                                                    │
                 ┌──────────────────────────┬───────┴──────────────────┬──────────────────────────┐
                 ▼                          ▼                          ▼                          ▼
      +--------------------+      +--------------------+      +--------------------+      +--------------------+
      |    PDFPayload      |      |    EmailPayload    |      |  DashboardPayload  |      |     ApiPayload     |
      +--------------------+      +--------------------+      +--------------------+      +--------------------+
      | - executive_summary|      | - cold_teaser_text |      | - tabular_columns  |      | - json_schema      |
      | - detailed_narrative|     | - short_callout    |      | - filter_tags      |      | - webhook_sig      |
      | - pdf_tag_layout   |      | - sales_angle      |      | - dashboard_cards  |      | - raw_data_dict    |
      +--------------------+      +--------------------+      +--------------------+      +--------------------+
```

* **Single Owner:** `src/presentation/payload_compiler.py`
* **Lifecycle:** Derived from `SessionBundle` by `PresentationCompiler` ➔ Passed to respective Output Driver.

### 8. `ExecutiveAuditReport` (IMMUTABLE DRIVER DTO)
* **Purpose:** Driver DTO for rendering a single-store 1-Page PDF audit. Holds a reference link, NOT a full embedded SessionBundle copy.
* **Fields:** `report_id` (UUIDv4), `store_domain` (str), `session_ref_id` (UUIDv4), `tenant` (TenantConfig), `pdf_payload` (PDFPayload).
* **Single Owner:** `src/presentation/drivers/pdf_driver.py`
* **Lifecycle:** Constructed at render time ➔ Passed to PDF template.
* **Validation Rules:** `session_ref_id` must point to a valid serialized `SessionBundle`.

### 9. `CandidateScoreRecord` (INTERNAL SELECTION ARTIFACT)
* **Purpose:** Internal scoring artifact used during evidence candidate evaluation. Banned from Domain Model API.
* **Fields:** `sidecar_path` (str), `total_score` (int), `scoring_reasons` (list[str]), `validation_passed` (bool).
* **Single Owner:** `src/selection/internal/evidence_scorer.py` (Internal package scope).
* **Lifecycle:** Created during selection globbing ➔ Ranked ➔ Logged to `reports/screenshot_selection_log.json`.

---

## 4. Object Ownership & Mutation Rules

```
+-----------------------------------------------------------------------------------+
|                           OBJECT MUTATION RULE MATRIX                             |
+-----------------------------------------------------------------------------------+
```

| Object Name | Category | Created By | Can Be Mutated By | Mutation Phase Window | Read By |
|---|---|---|---|---|---|
| `StoreRecord` | Domain | `store_loader.py` | None | Ingestion Only | `core_scanner.py` |
| `ScanContext` | **Transient State** | `core_scanner.py` | `variant_matrix.py`, `bis_checker.py` | Active Scan Window | `EvidenceBuilder` (Destroyed after) |
| `VisualEvidence` | Domain | `evidence_collector.py` | `visual_verifier.py` | Capture Window | `SessionBundle`, Renderers |
| `BoundingBoxMap`| Domain | `bounding_box_extractor.py`| None | Capture Window | `SessionBundle`, Renderers |
| `CommercialImpact`| Domain | `impact_calculator.py`| None | Post-Scan Window | `SessionBundle`, Renderers |
| `SessionBundle` | **Immutable Asset** | `session_serializer.py` | **NONE (STRICTLY READ-ONLY)** | Sealed at Serialization | Candidate Selector, All Output Drivers |
| `PresentationPayloads`| Driver DTOs | `payload_compiler.py`| None | Compilation Window | Output Drivers (PDF, Teaser, HTML, API) |
| `ExecutiveAuditReport`| Driver DTO | `pdf_driver.py` | None | Render Window | PDF Engine |

---

## 5. Architectural Decision Records (ADRs)

### ADR-DM-001: Separation of Transient ScanContext from SessionBundle
* **Status:** Accepted
* **Context:** V1 serialized scraping workspace state directly into sidecar JSON files, coupling internal scanner mechanics to stored evidence artifacts.
* **Decision:** `ScanContext` is strictly transient memory. It is passed to `EvidenceBuilder` to construct a sealed `SessionBundle` and then immediately garbage collected.
* **Consequences:** `SessionBundle` contains zero scanner execution clutter.

### ADR-DM-002: Output Driver Decoupling Architecture
* **Status:** Accepted
* **Context:** V1 assumed the scanner's primary goal was rendering an HTML report.
* **Decision:** The Scanner Engine outputs an immutable `SessionBundle`. Deliverables (PDF, Teaser PNG, Benchmark HTML, Webhooks) are independent **Output Drivers** consuming the bundle.
* **Consequences:** Adding new integrations (Klaviyo, HubSpot, CRM API) requires adding a new driver without touching scanner or evidence code.
