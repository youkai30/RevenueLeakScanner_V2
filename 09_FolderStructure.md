# 09 Folder Structure — Revenue Leak Scanner V2

## 1. Complete System Directory Tree

The target codebase for Revenue Leak Scanner V2 is organized into explicit, layer-isolated packages. It cleanly separates application source code, execution entry points, domain models, output templates, and architecture documentation.

```
RevenueLeakScanner_V2/
├── README.md                           # Master Architecture Index & Sitemap
├── 01_SystemVision.md                  # Vision, Pillars, Philosophy, & Scope Boundaries
├── 02_BusinessModel.md                 # Commercial Personas, Deliverables, & Revenue Models
├── 03_ProductRequirements.md           # FR, NFR, Traceability Matrix, & Use Cases
├── 04_SystemArchitecture.md            # C4 Diagrams, 5-Layer Boundaries, & Process Pool Model
├── 05_RuntimePipeline.md               # Detailed Execution Stages & Runtime Calls
├── 06_ModuleResponsibilities.md       # SRP Specifications for Every System Package
├── 07_DataOwnership.md                 # Taxonomy of Data Owners, Writers, & Readers
├── 08_EvidencePackage.md               # Session Bundle Specification & JSON Schemas
├── 09_FolderStructure.md               # File Tree Specification & Package Boundaries
├── 10_FileInventory.md                 # Comprehensive Inventory of Proposed V2 Files
├── 11_StateMachine.md                  # Audit State Machine & State Lifecycle Rules
├── 12_DataFlow.md                      # Data Lineage, Transformation, & Input/Output Mapping
├── 13_SystemInvariants.md              # Governing Invariants & Automated Check Rules
├── 14_CommercialPipeline.md            # Commercial Loss Engine & Lead Scoring Logic
├── 15_ReportArchitecture.md            # Template Engine Drivers (PDF, PNG, HTML)
├── 16_DemoArchitecture.md              # Fixture-Based Demo Engine Architecture
├── 17_ScannerArchitecture.md           # Playwright DOM Scraper & Settlement Mechanics
├── 18_RefactorStrategy.md              # Transition Roadmap from V1 Legacy Codebase
├── 19_ImplementationRoadmap.md         # Phase-by-Phase Implementation Schedules
├── 20_RiskAnalysis.md                  # Risk Mitigation & Failure Mode Matrix
│
├── src/                                # Core Application Source Package
│   ├── __init__.py
│   ├── config.py                       # Global Immutable Constants & Configuration
│   ├── exceptions.py                   # Custom Exception Taxonomy
│   │
│   ├── ingestion/                      # Layer 1: Data Ingestion & Batch Loading
│   │   ├── __init__.py
│   │   ├── store_loader.py             # CSV / JSON Target Store Ingestion
│   │   └── tenant_config.py            # Agency White-Label Configuration Loader
│   │
│   ├── scanner/                        # Layer 2: Playwright Inspection Engine
│   │   ├── __init__.py
│   │   ├── browser_factory.py          # Process-Isolated Playwright Browser Pool
│   │   ├── core_scanner.py             # Integrated Store PDP Inspection Runner
│   │   ├── product_discovery.py        # PDP URL Crawler & Discovery Engine
│   │   ├── variant_matrix.py           # Dynamic Variant Selection & OOS Clicker
│   │   ├── bis_checker.py              # Back-in-Stock Form & Modal Inspector
│   │   └── cro_stack_detector.py       # Review Widget, Upsell, & Sticky ATC Scraper
│   │
│   ├── evidence/                       # Layer 3: Evidence Capture & Verification
│   │   ├── __init__.py
│   │   ├── evidence_collector.py       # Page Scrolling, Overlay Manager, & Capture
│   │   ├── bounding_box_extractor.py   # DOM Coordinate & Spatial Math Extractor
│   │   ├── visual_verifier.py          # Pillow Image Quality & Blank Canvas Gate
│   │   └── session_serializer.py       # UUID Session Directory & JSON Builder
│   │
│   ├── selection/                      # Layer 4: Evidence Ranking & Validation Gate
│   │   ├── __init__.py
│   │   ├── candidate_selector.py       # Session Bundle Discovery Engine
│   │   ├── evidence_scorer.py          # Ranking Heuristics & Score Calculator
│   │   └── ground_truth_validator.py   # Assertion Rule Checker & Validation Gate
│   │
│   ├── commercial/                     # Commercial Impact Engine
│   │   ├── __init__.py
│   │   ├── impact_calculator.py        # Lost Revenue ($/month) Financial Model
│   │   └── lead_prioritizer.py         # Agency Lead Quality & Fit Scoring
│   │
│   └── presentation/                   # Layer 5: Deliverable Template Drivers
│       ├── __init__.py
│       ├── payload_compiler.py         # Session Bundle Presentation Data Builder
│       ├── annotation_math.py          # Collision-Free Tag Placement Calculator
│       ├── drivers/                    # Multi-Format Output Drivers
│       │   ├── __init__.py
│       │   ├── pdf_driver.py           # 1-Page Executive PDF Renderer (WeasyPrint)
│       │   ├── teaser_driver.py        # Cold Email Cropped PNG Teaser Generator
│       │   └── html_driver.py          # Standalone Interactive HTML Benchmark
│       └── templates/                  # Presentation HTML/CSS Templates
│           ├── executive_pdf.html
│           ├── cold_teaser.html
│           └── benchmark_report.html
│
├── storage/                            # Physical Runtime Output Directories
│   ├── sessions/                       # Session Bundles (screenshots/<domain>/<session_id>/)
│   ├── reports/                        # Output PDFs, Teaser PNGs, & HTML Audits
│   └── fixtures/                       # Pre-Recorded Demo Scans & Network Fixtures
│
├── scripts/                            # CLI Execution Wrappers
│   ├── run_production_scan.py          # Master CLI for Batch Production Scanning
│   └── run_demo_build.py               # Fixture-Based Demo Report Builder
│
└── tests/                              # Automated Test Suite
    ├── unit/                           # Unit Tests per Package Layer
    ├── integration/                    # Pipeline Parity & End-to-End Tests
    └── verification/                   # System Invariant & Checksum Assertion Tests
```

---

## 2. Layer Package Mapping

```
+-----------------------------------------------------------------------------------+
|                           LAYER TO PACKAGE MAPPING                                |
+-----------------------------------------------------------------------------------+
```

| Architectural Layer | Package Path | Encapsulated Responsibility |
|---|---|---|
| **Layer 1: Ingestion** | `src/ingestion/` | Parses input datasets, loads tenant branding, and prepares batch records. |
| **Layer 2: Scanner** | `src/scanner/` | Drives Playwright instances, navigates DOMs, selects variants, and checks BIS forms. |
| **Layer 3: Evidence** | `src/evidence/` | Scrolls viewports, captures screenshots, extracts bounding boxes, and writes `SessionBundle`. |
| **Layer 4: Selection** | `src/selection/` | Globs session directories, scores candidates, and enforces validation assertions. |
| **Layer 5: Presentation**| `src/presentation/`| Compiles presentation payloads and renders single-store PDFs, Teasers, and HTML. |
| **Commercial Layer** | `src/commercial/` | Computes financial lost revenue ($/mo) and agency lead priority scores. |

---

## 3. Package Import Rules & Boundaries

To enforce architectural integrity and prevent circular imports, Version 2 defines **Strict Import Boundary Rules**:

```
+-----------------------------------------------------------------------------------+
|                            STRICT IMPORT BOUNDARY RULES                           |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  RULE 1: DOWNWARD IMPORTS ONLY                                                    |
|          `src/presentation/` may import from `src/selection/` or `src/commercial/`,|
|          but `src/scanner/` is PROHIBITED from importing `src/presentation/`.     |
|                                                                                   |
|  RULE 2: NO CROSS-LAYER RE-EXPORTS                                                |
|          Compatibility shims (like V1's `screenshot_manager.py`) are strictly     |
|          banned. Packages must be imported directly from their primary path.       |
|                                                                                   |
|  RULE 3: ISOLATED TEST ACCESS                                                     |
|          Test suites in `tests/` may import any package, but source code in `src/` |
|          is PROHIBITED from importing from `tests/` or `scripts/`.                |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 4. Storage Directory Specifications

```
+-----------------------------------------------------------------------------------+
|                          STORAGE DIRECTORY SPECIFICATIONS                         |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. `storage/sessions/<domain>/<session_id>/`                                     |
|     - Contains atomic `session_<uuid>.png` and `session_<uuid>.json` sidecars.     |
|     - Read-only once serialized.                                                  |
|                                                                                   |
|  2. `storage/reports/<domain>/`                                                   |
|     - Stores generated client deliverables (`audit.pdf`, `teaser.png`).           |
|                                                                                   |
|  3. `storage/fixtures/<domain>/`                                                  |
|     - Contains pre-recorded production session bundles for demo mode execution.  |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 5. Architectural Decision Records (ADRs)

### ADR-FS-001: Separation of Source Code (`src/`) from Runtime Storage (`storage/`)
* **Status:** Accepted
* **Context:** V1 stored outputs, logs, and screenshots directly in root application folders, complicating deployment and version control.
* **Decision:** V2 enforces complete separation. All source code lives in `src/`, while physical outputs live in `storage/` (which is excluded from Git).
* **Consequences:** Clean repository layout; simple Docker volume mounting for persistent storage.

### ADR-FS-002: Modular Multi-Format Presentation Drivers
* **Status:** Accepted
* **Context:** V1 embedded presentation CSS and HTML strings directly inside Python generator scripts.
* **Decision:** V2 establishes `src/presentation/drivers/` and `src/presentation/templates/`, separating driver logic from HTML/CSS assets.
* **Consequences:** Templates can be updated or white-labeled without modifying Python rendering code.
