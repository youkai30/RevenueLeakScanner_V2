# 04 System Architecture — Revenue Leak Scanner V2

## 1. High-Level System Architecture (C4 Container Diagram)

Revenue Leak Scanner V2 is designed as a process-isolated, modular, and single-source-of-truth system. It strictly separates data ingestion, extraction, session serialization, selection validation, and presentation rendering.

```
+---------------------------------------------------------------------------------------------------+
|                                 SYSTEM ARCHITECTURE CONTAINER DIAGRAM                             |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  +-----------------------+        +-----------------------+        +---------------------------+  |
|  |     INPUT LAYER       |        |   PARALLEL SCANNER    |        |     EVIDENCE CAPTURE      |  |
|  |                       |        |        WORKERS        |        |          ENGINE           |  |
|  |  - CSV Loader         | ──►    |  - Playwright Worker  | ──►    |  - DOM Overlay Manager    |  |
|  |  - Domain Normalizer  |        |  - Dynamic Variant    |        |  - BoundingBox Extractor  |  |
|  |  - Tenant Config      |        |  - BIS Modal Checker  |        |  - Pillow Verification    |  |
|  +-----------------------+        +-----------------------+        +---------------------------+  |
|                                                                                  │                |
|                                                                                  ▼                |
|  +-----------------------+        +-----------------------+        +---------------------------+  |
|  |  PRESENTATION ENGINE  |        |  SELECTION & VALIDATION|       |      SESSION BUNDLE       |  |
|  |                       |        |        ENGINE         |        |         STORAGE           |  |
|  |  - Teaser PNG Engine  | ◄──    |  - Evidence Scorer    | ◄──    |  - UUID Session Folder    |  |
|  |  - Executive PDF      |        |  - Ground-Truth Gate  |        |  - Immutable JSON Sidecar |  |
|  |  - Benchmark HTML     |        |  - Assertion Checking |        |  - SHA-256 Sealed PNG     |  |
|  +-----------------------+        +-----------------------+        +---------------------------+  |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Structural Layer Boundaries & Component Isolation

To prevent state leakage and circular dependencies, the system is strictly divided into **5 Encapsulated Layers**:

```
+-----------------------------------------------------------------------------------+
|                              FIVE ARCHITECTURAL LAYERS                            |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  LAYER 1: INGESTION & ORCHESTRATION                                               |
|  - Manages batch store inputs, worker thread pool, and CLI execution parameters.  |
|  - Banned from inspecting DOM elements or rendering HTML/PDFs directly.          |
|                                                                                   |
|  LAYER 2: SCANNER & EXTRACTION ENGINE                                             |
|  - Interacts with live Playwright pages, selects variants, & checks BIS forms.   |
|  - Banned from writing presentation copy or rendering final user deliverables.     |
|                                                                                   |
|  LAYER 3: EVIDENCE & SESSION SERIALIZATION                                        |
|  - Captures PNG screenshots, extracts bounding boxes, & seals Session Bundles.     |
|  - Banned from altering scanner findings or injecting unverified metadata.        |
|                                                                                   |
|  LAYER 4: SELECTION & VALIDATION GATE                                             |
|  - Globs session bundles, evaluates ground-truth rules, & ranks candidate evidence|
|  - Banned from mutating Session Bundle contents on disk.                           |
|                                                                                   |
|  LAYER 5: PRESENTATION & DELIVERABLE ENGINE                                       |
|  - Reads Session Bundles and renders single-store PDFs, Teasers, and Benchmark HTML|
|  - Banned from calling Playwright or hardcoding brand/presentation data in code.  |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 3. Component Interaction & Sequence Flow

```
[ Ingestion Layer ]        [ Scanner Layer ]        [ Evidence Layer ]        [ Validation Layer ]     [ Presentation Layer ]
         │                         │                         │                         │                         │
 1. Send StoreRecord ─────────────►│                         │                         │                         │
         │                         │ 2. Navigate & Select OOS│                         │                         │
         │                         ├────────────────────────►│                         │                         │
         │                         │                         │ 3. Capture PNG & Boxes  │                         │
         │                         │                         ├────────────────────────►│                         │
         │                         │                         │                         │ 4. Score & Validate     │
         │                         │                         │                         ├────────────────────────►│
         │                         │                         │                         │                         │ 5. Render PDF/PNG/HTML
```

---

## 4. Architectural Boundaries & Data Flow Constraints

```
+-----------------------------------------------------------------------------------+
|                            DATA FLOW CONSTRAINT RULES                             |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  RULE 1: DOWNWARD & RIGHTWARD DATA FLOW ONLY                                      |
|          Data flows strictly: Input ➔ Scanner ➔ Evidence ➔ Validation ➔ Render    |
|          Reverse data passes (e.g. Presentation engine calling Scanner) are BANNED.|
|                                                                                   |
|  RULE 2: READ-ONLY SELECTION GATE                                                 |
|          The Validation Engine reads Session Bundles from disk; it NEVER mutates  |
|          sidecar JSONs or re-names screenshot files during scoring.               |
|                                                                                   |
|  RULE 3: PURE RENDERERS                                                           |
|          Renderers accept a validated `SessionBundle` dict. They possess ZERO      |
|          internal brand lookup dictionaries (`SAMPLE_STORES` is eliminated).      |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 5. System Deployment & Concurrency Architecture

To guarantee process-level Playwright driver isolation and scale across multi-core server environments, Version 2 implements a **ProcessPool Worker Model**:

```
                                  +-----------------------------------+
                                  |     Main Orchestrator Process     |
                                  +-----------------------------------+
                                                    │
                                                    │ Spawns Isolated OS Processes
                                                    ▼
+-----------------------------------+-----------------------------------+-----------------------------------+
|         Worker Process 1          |         Worker Process 2          |         Worker Process N          |
|  +-----------------------------+  |  +-----------------------------+  |  +-----------------------------+  |
|  | Dedicated Playwright Instance|  |  | Dedicated Playwright Instance|  |  | Dedicated Playwright Instance|  |
|  +-----------------------------+  |  +-----------------------------+  |  +-----------------------------+  |
|  | Isolated Memory Heap        |  |  | Isolated Memory Heap        |  |  | Isolated Memory Heap        |  |
|  +-----------------------------+  |  +-----------------------------+  |  +-----------------------------+  |
|  | Dedicated Temp Session Dir  |  |  | Dedicated Temp Session Dir  |  |  | Dedicated Temp Session Dir  |  |
|  +-----------------------------+  |  +-----------------------------+  |  +-----------------------------+  |
+-----------------------------------+-----------------------------------+-----------------------------------+
                                                    │
                                                    │ Consolidates Output Bundles
                                                    ▼
                                  +-----------------------------------+
                                  |     Deterministic Storage Engine  |
                                  +-----------------------------------+
```

---

## 6. System Architecture Decision Records (ADRs)

### ADR-SA-001: Strict Layer Separation & Isolation
* **Status:** Accepted
* **Context:** V1 allowed presentation modules (`generate_opportunity_report.py`) to invoke file system globbing and perform selection logic directly, causing architectural coupling.
* **Decision:** V2 enforces strict 5-layer separation. Modules in Layer 5 (Presentation) are prohibited from importing modules from Layer 2 (Scanner) or performing file discovery.
* **Consequences:** Clean interface contracts between layers; simplified unit testing and mocking.

### ADR-SA-002: ProcessPool Worker Model over Thread Pools
* **Status:** Accepted
* **Context:** Playwright's C-bindings and event loops can suffer from deadlock or race conditions when run in multi-threaded Python environments.
* **Decision:** V2 enforces process-level isolation (`ProcessPoolExecutor`). Each worker process manages its own independent Playwright lifecycle and OS-level memory heap.
* **Consequences:** 100% thread-safe execution; memory leaks in third-party browser drivers are isolated and destroyed upon process exit.
