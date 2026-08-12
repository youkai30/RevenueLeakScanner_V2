# 08 Runtime Pipeline Specification — Revenue Leak Scanner V2

## 1. Executive Summary & Runtime Laws

The Runtime Pipeline of Revenue Leak Scanner V2 defines the end-to-end execution sequence, data flows, and state transitions from raw target store ingestion to sealed Session Bundle creation and deliverable output generation.

```
+-----------------------------------------------------------------------------------+
|                             RUNTIME PIPELINE GOVERNING LAW                        |
+-----------------------------------------------------------------------------------+
|  "The scanner engine outputs an immutable Session Bundle. All deliverables        |
|   (PDFs, Teasers, HTML, Webhooks) are pure Downstream Drivers consuming           |
|   the sealed bundle payload. Reverse data flow or state mutation is BANNED."      |
+-----------------------------------------------------------------------------------+
```

---

## 2. Canonical Target Architecture Runtime Flow

```
StoreRecord (Ingestion)
    │
    ▼
Scanner Engine (Playwright Isolation)
    │
    ▼
Transient ScanContext (In-Memory Scraping Workspace)
    │
    ▼
Commercial Impact Engine (Dollar Loss Calculation)
    │
    ▼
EvidenceBuilder (Visual Verification & Sealing)
    │
    ▼
IMMUTABLE SessionBundle (Sealed SHA-256 Storage)
    │
    ├──────────────────┬──────────────────┬──────────────────┐
    ▼                  ▼                  ▼                  ▼
PDF Driver         Teaser Driver     Dashboard Driver    API / CRM Driver
(audit.pdf)        (teaser.png)      (benchmark.html)    (Webhook Payload)
```

---

## 3. Step-by-Step Runtime Execution Flow

### Stage 1: Ingestion & Environment Preparation
1. `run_production_scan.py` (CLI wrapper) invokes `src/ingestion/store_loader.py`.
2. Target CSV/JSON records are validated and transformed into immutable `StoreRecord` DTOs.
3. `ProcessPoolExecutor` spawns dedicated worker processes. Each process initializes its own `BrowserFactory` with a process-isolated Playwright instance.

### Stage 2: Scanner Execution & Transient Context Generation
1. `src/scanner/core_scanner.py` receives a `StoreRecord` and opens a clean Playwright `Page`.
2. `product_discovery.py` discovers PDP URLs; `variant_matrix.py` dynamic selector clicks unavailable SKUs.
3. `bis_checker.py` and `cro_stack_detector.py` evaluate DOM, shadow DOM, and network requests.
4. All scraping findings populate a transient `ScanContext` dictionary in memory.

### Stage 3: Commercial Intelligence Processing
1. `src/commercial/impact_calculator.py` receives the `ScanContext`.
2. Calculates `est_monthly_loss_usd` using the financial formula and assigns `lead_priority` (`HIGH`, `MEDIUM`, `LOW`).
3. Appends calculated `CommercialImpact` attributes into `ScanContext`.

### Stage 4: Atomic Evidence Capture & Bundle Sealing
1. `src/evidence/evidence_collector.py` scrolls the page and dismisses noise overlays.
2. `bounding_box_extractor.py` queries DOM spatial coordinates (`x, y, w, h`).
3. Playwright captures the PNG screenshot; `visual_verifier.py` executes Pillow/extrema assertions (`width >= 1024`, `valid == True`).
4. `session_serializer.py` invokes `EvidenceBuilder` to merge facts, hashes, and boxes into a `SessionBundle`.
5. SHA-256 checksum is generated and written to `storage/sessions/<domain>/<session_id>/session_<id>.checksum`.
6. **`ScanContext` is destroyed/garbage collected.**

### Stage 5: Downstream Output Driver Execution
1. Downstream drivers discover and load verified `SessionBundle` objects.
2. `src/presentation/payload_compiler.py` generates driver-specific presentation DTOs (`PDFPayload`, `EmailPayload`, `DashboardPayload`).
3. Output drivers render final commercial deliverables without modifying the session bundle:
   * `pdf_driver.py` ➔ Renders 1-Page Executive PDF (`audit.pdf`).
   * `teaser_driver.py` ➔ Crops image and overlays outreach teaser (`teaser.png`).
   * `html_driver.py` ➔ Renders interactive benchmark deck (`benchmark.html`).
   * `api_driver.py` ➔ Pushes JSON payloads to agency CRM/Webhooks.

---

## 4. Explicit Negative Constraints (What the Pipeline MUST NOT Do)

To enforce strict architectural discipline, the V2 Runtime Pipeline explicitly forbids the following legacy practices:

```
+-----------------------------------------------------------------------------------+
|                        NEGATIVE RUNTIME CONSTRAINTS (BANNED)                      |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. DO NOT copy V1 files and fix bugs line-by-line.                              |
|  2. DO NOT reuse or import the legacy SAMPLE_STORES python dictionary.           |
|  3. DO NOT make the Report Builder responsible for business or scanning logic.    |
|  4. DO NOT allow Demo mode to write directly into production storage without      |
|     executing scanner/validator fixtures.                                        |
|  5. DO NOT pass untyped, raw Python dictionaries between layers.                  |
|  6. DO NOT generate HTML reports first and attempt to attach PDFs as a side-effect. |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 5. Implementation Execution Roadmap (Phases A through G)

```
================================================================================
                    V2 STEP-BY-STEP IMPLEMENTATION ROADMAP
================================================================================

 [ PHASE A: FOUNDATION & STORAGE INFRASTRUCTURE ]
   ├── Pydantic domain models & SessionBundle DTOs
   ├── Checksum calculation & SHA-256 sealing modules
   ├── Session-isolated directory manager (`storage/sessions/<domain>/<session_id>/`)
   └── Global configuration, logging, and custom exception hierarchy

 [ PHASE B: SCANNER ENGINE ]
   ├── Target store ingestion & domain normalizer (`src/ingestion/`)
   ├── Process-isolated Playwright browser pool (`src/scanner/browser_factory.py`)
   ├── PDP Discovery, Dynamic Variant Matrix Scanner, & BIS Modal Inspector
   └── Integrated Store Scanner runner

 [ PHASE C: COMMERCIAL INTELLIGENCE ENGINE ]
   ├── Lost Revenue Impact Calculator ($/month calculation model)
   ├── Agency Lead Priority Engine (`HIGH`, `MEDIUM`, `LOW`)
   └── Confidence Engine & App Stack Evaluator

 [ PHASE D: EVIDENCE EXTRACTION & BUNDLE SERIALIZER ]
   ├── Viewport Scrolling, Overlay Manager, & Playwright Screenshot Capture
   ├── DOM Bounding Box Extractor
   ├── Pillow Visual Verification Gate (`valid` flag & blank canvas detection)
   └── `EvidenceBuilder` & Immutably Sealed `SessionBundle` Serializer

 [ PHASE E: OUTPUT DRIVERS (DELIVERABLES) ]
   ├── Presentation Payload Compiler (PDFPayload, EmailPayload, DashboardPayload)
   ├── 1-Page Executive Audit PDF Driver (WeasyPrint / HTML Template Engine)
   ├── Cold Email Outreach Teaser PNG Driver (Cropped Image Generator)
   ├── Standalone Interactive HTML Benchmark Driver
   └── CRM / Webhook API Payload Exporter

 [ PHASE F: VERIFICATION & TESTING AUTOMATION ]
   ├── Layer-by-layer Unit Tests
   ├── Pipeline Parity Tests (Demo vs Production execution verification)
   ├── System Invariant & SHA-256 Checksum Tamper Assertions
   └── Single Source of Truth Consistency Asserter

 [ PHASE G: COMMERCIAL QUALITY ASSURANCE ]
   ├── Cold outreach deliverability & image size audit (< 200KB check)
   ├── Single-store PDF executive review & sales copy audit
   ├── SDR workflow verification & lost revenue dollar clarity audit
   └── End-to-end agency prospecting trial run

================================================================================
```

---

## 6. Architectural Decision Records (ADRs)

### ADR-RP-001: Transient ScanContext Destruction
* **Status:** Accepted
* **Context:** V1 allowed scraping workspace data to bleed into reporting layers, creating data ownership confusion.
* **Decision:** `ScanContext` is strictly transient. Once passed to `EvidenceBuilder` and serialized into a sealed `SessionBundle`, `ScanContext` is explicitly destroyed.
* **Consequences:** Eliminates memory leaks and prevents downstream modules from accessing stale workspace state.

### ADR-RP-002: Output Driver Modular Extension Model
* **Status:** Accepted
* **Context:** V1 coupled report generation to HTML output rendering.
* **Decision:** Output drivers subscribe as read-only consumers of `SessionBundle` objects.
* **Consequences:** New output targets (HubSpot integration, Slack alerts, PDF decks) can be added without modifying the core scanner or evidence code.
