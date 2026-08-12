# 03 Product Requirements — Revenue Leak Scanner V2

## 1. Functional Requirements (FR)

Functional requirements define the core operational capabilities that Version 2 must execute across scanning, extraction, validation, and presentation.

```
+-----------------------------------------------------------------------------------+
|                        FUNCTIONAL REQUIREMENTS HIERARCHY                          |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  FR-1: Automated Store & PDP Discovery Engine                                     |
|  FR-2: Dynamic Variant & Out-of-Stock Matrix Inspection                           |
|  FR-3: Back-in-Stock & Restock Alert Verification                                |
|  FR-4: Atomic Evidence Capture & Checksum Sealing                                 |
|  FR-5: Commercial Impact & Revenue Leak Calculation                               |
|  FR-6: Multi-Format Asset Generation (Image, PDF, HTML)                           |
|  FR-7: Single-Source Presentation & Rendering Engine                              |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

### Detailed Functional Requirements Breakdown

| Requirement ID | Module / Feature Area | Detailed Requirement Specification | Acceptance Criteria |
|---|---|---|---|
| **FR-1.1** | Store Discovery | Must accept store domain inputs (CSV, JSON, CLI) and discover valid PDP URLs via `/products.json`, sitemaps, or collection crawling. | Discovers at least 1 out-of-stock PDP or reports `NO_OOS_VARIANTS`. |
| **FR-1.2** | Variant Matrix | Must dynamically interact with size/color/style DOM selectors to isolate out-of-stock variants. | Triggers OOS DOM state transition and waits for settlement. |
| **FR-2.1** | BIS Modal Detection | Must inspect DOM, Network requests, and Shadow DOM for active Back-in-Stock capture forms (Klaviyo, Omnisend, etc.). | Correctly flags `notify_button_detected = True/False`. |
| **FR-2.2** | CRO Stack Auditing | Must detect installed review widgets (Yotpo, Okendo, Loox), upsell apps, and sticky add-to-cart bars. | Records presence and exact app platform in metadata payload. |
| **FR-3.1** | Evidence Capture | Must capture a full-viewport PNG screenshot AND extract spatial bounding boxes (`x, y, w, h`) of key DOM elements at the exact millisecond of state settlement. | Generates atomic PNG + JSON pair sealed with matching UUID. |
| **FR-3.2** | Visual Verification | Must run Pillow/OCR checks on captured PNG bytes to assert that image width/height $\ge 1024\times600$ and image is non-blank. | Marks `valid = True/False` in session payload. |
| **FR-4.1** | Revenue Loss Calculation | Must calculate estimated monthly lost revenue dollars ($/mo) based on estimated traffic, OOS ratio, baseline CR, and product price. | Injects quantified dollar loss into Session Bundle. |
| **FR-5.1** | Multi-Format Rendering | Must generate: (1) 1-Page Executive PDF, (2) Cold Pitch Image Teaser, and (3) Interactive HTML Benchmark Report. | 100% of rendered values originate from `SessionBundle`. |

---

## 2. Non-Functional Requirements (NFR)

Non-functional requirements specify system quality attributes, performance targets, and operational constraints.

```
+-----------------------------------------------------------------------------------+
|                      NON-FUNCTIONAL REQUIREMENTS SPECIFICATION                    |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  NFR-1: ACCURACY & ZERO FALSE POSITIVES                                           |
|        Zero false positive revenue leak classifications. All claims must pass      |
|        100% of automated rule assertions.                                         |
|                                                                                   |
|  NFR-2: PERFORMANCE & SCALABILITY                                                 |
|        Full store scan execution time < 15 seconds per store in process-isolated   |
|        workers. Parallel execution scalability across multi-core CPU pools.       |
|                                                                                   |
|  NFR-3: DETERMINISM & REPRODUCIBILITY                                             |
|        Identical Session Bundle inputs MUST yield bit-for-bit identical PDF/HTML   |
|        and Teaser Image outputs across environments.                              |
|                                                                                   |
|  NFR-4: SECURITY & TENANT ISOLATION                                               |
|        Process-level isolation for Playwright instances. Zero cross-tenant        |
|        data leakage or file system collisions in multi-agency environments.       |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 3. Use Case Specifications

### Use Case UC-1: SDR Cold Prospecting Outreach

```
+-----------------------+--------------------------------------------------------------------+
| Attribute             | Specification                                                      |
+-----------------------+--------------------------------------------------------------------+
| Actor                 | Agency SDR / Business Development Representative                   |
| Pre-conditions        | Target store list (CSV) provided to Revenue Leak Scanner V2.       |
| Trigger               | SDR initiates bulk prospecting run for target apparel category.     |
| Main Flow             | 1. System scans 100 apparel stores in parallel workers.            |
|                       | 2. System filters top 10 stores with highest estimated lost revenue|
|                       | 3. System outputs `teaser.png` and `audit.pdf` for each store.     |
|                       | 4. SDR attaches `teaser.png` directly into cold email / LinkedIn message|
| Post-conditions       | Prospect receives personalized, visually verified revenue leak proof|
| Alternative Flows     | Store has no OOS variants ➔ System flags `NO_LEAK` and excludes.   |
+-----------------------+--------------------------------------------------------------------+
```

### Use Case UC-2: Account Executive Pitch Meeting Preparation

```
+-----------------------+--------------------------------------------------------------------+
| Attribute             | Specification                                                      |
+-----------------------+--------------------------------------------------------------------+
| Actor                 | Agency Account Executive / Lead CRO Strategist                     |
| Pre-conditions        | Sales discovery call booked with E-Commerce Founder / CMO.          |
| Trigger               | AE inputs prospect domain (`toms.com`) into V2 audit engine.       |
| Main Flow             | 1. System executes deep scan of PDP, cart, and restock flows.      |
|                       | 2. System calculates exact monthly lost revenue ($24,480/mo).      |
|                       | 3. System compiles 1-Page Executive PDF with white-labeled branding|
|                       | 4. AE presents PDF during discovery call to justify agency retainer|
| Post-conditions       | Prospect receives executive pitch document anchoring project ROI.   |
+-----------------------+--------------------------------------------------------------------+
```

---

## 4. User Personas & Feature Mapping

```
+-----------------------------------------------------------------------------------+
|                        PERSONA TO FEATURE MAPPING MATRIX                          |
+-----------------------------------------------------------------------------------+
```

| Feature / Capability | Agency Founder | Cold Outreach SDR | CRO Account Exec | Technical Auditor |
|---|---|---|---|---|
| Bulk Parallel Store Scanning | **HIGH** | **HIGH** | Low | Low |
| Lost Revenue Calculator ($/mo) | **HIGH** | **HIGH** | **HIGH** | Low |
| Cold Pitch Image Teaser (`teaser.png`) | Medium | **CRITICAL** | Low | Low |
| 1-Page Executive Audit PDF (`audit.pdf`) | Medium | Medium | **CRITICAL** | Low |
| CRO App Stack Detection (Reviews/Upsell) | Medium | Medium | **HIGH** | **HIGH** |
| SHA-256 Checksum & Verification Logs | Low | Low | Medium | **CRITICAL** |
| Custom White-Label Agency Branding | **HIGH** | Low | **HIGH** | Low |

---

## 5. Traceability Matrix (Business Requirements ➔ System Specifications)

```
+-----------------------------------------------------------------------------------+
|                                TRACEABILITY MATRIX                                |
+-----------------------------------------------------------------------------------+
```

| Business Goal (from `02_BusinessModel`) | Product Requirement (FR/NFR) | Architectural Target Component |
|---|---|---|
| Provide unassailable visual proof | **FR-3.1, FR-3.2, NFR-1** | `EvidenceCollector` + Pillow Verification Gate |
| SDR Cold Outreach Deliverability | **FR-5.1 (Teaser PNG)** | `AssetRenderer` (Teaser Cropper) |
| Quantify ROI in Lost Revenue Dollars | **FR-4.1** | `CommercialImpactEngine` |
| White-Label Agency Customization | **NFR-4** | `TenantConfig` + Template Renderer Driver |
| Prevent False Positive Customer Claims | **NFR-1** | `EvidenceValidator` Assertion Gate |
| Ensure Deterministic Output Generation | **NFR-3** | `SessionBundle` Single Source of Truth |

---

## 6. Product Requirement Architecture Decisions (ADRs)

### ADR-PR-001: Mandatory Pillow & OCR Verification Gate
* **Status:** Accepted
* **Context:** Scraped DOM data can occasionally desynchronize from rendered browser pixels (e.g. dynamic modal render delays).
* **Decision:** All screenshots captured by `EvidenceCollector` MUST pass a multi-point visual verification check (Pillow extrema check + minimum dimension bounds) before session payload serialization.
* **Consequences:** Invalid or blank screenshots fail early and are flagged as `VALIDATION_FAILED`, preventing corrupt assets from reaching output reports.

### ADR-PR-002: Multi-Format Asset Decoupling
* **Status:** Accepted
* **Context:** Legacy V1 only generated a monolithic HTML file, limiting outreach versatility.
* **Decision:** Product requirements mandate three separate rendering target drivers (Image Crop, PDF Engine, HTML Renderer) accepting identical `SessionBundle` payloads.
* **Consequences:** Rendering logic is cleanly decoupled from data extraction and scoring.
