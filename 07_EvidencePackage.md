# 07 Evidence Package Specification — Revenue Leak Scanner V2

## 1. Executive Summary & Evidence Laws

The Evidence Package (`SessionBundle`) is the core immutable domain asset of Revenue Leak Scanner V2. It is the sole data contract connecting the Playwright Scanner Engine to downstream Output Drivers (PDF Generator, Teaser Image Generator, Benchmark HTML Renderer, and CRM Webhooks).

```
+-----------------------------------------------------------------------------------+
|                            EVIDENCE INTEGRITY LAWS                                |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  LAW 1: ATOMIC CAPTURE                                                            |
|  Every visual proof artifact (PNG screenshot) and spatial coordinate map           |
|  (bounding boxes) MUST be captured during the exact same millisecond window.      |
|                                                                                   |
|  LAW 2: SINGLE SCRIPTED SERIALIZATION                                             |
|  Session bundles are compiled exclusively by EvidenceBuilder at scan time.        |
|  Manual JSON file mutators and out-of-band copiers are strictly prohibited.       |
|                                                                                   |
|  LAW 3: DETERMINISTIC CHECKSUM SEALING                                            |
|  Every SessionBundle on disk is sealed with a SHA-256 checksum binding the PNG    |
|  pixel stream to the JSON metadata payload. Any tampering invalidates the bundle. |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 2. Session Bundle Physical Directory Architecture

Every completed scan run outputs a single, session-isolated bundle directory inside physical storage:

```
storage/sessions/<domain>/<session_id>/
├── session_<session_id>.json        # Sealed JSON Metadata Sidecar
├── session_<session_id>.png         # Visual Evidence Screenshot Asset (Primary Finding)
├── session_<session_id>_finding_<finding_id>.png  # Additional Visual Evidence (Optional)
└── session_<session_id>.checksum    # SHA-256 Checksum Signature Verification File
```

* **Zero Directory Pollution:** No orphan `*.meta.json` files live in un-scoped domain roots.
* **Read-Only Post-Serialization:** File permissions on the bundle directory are set to read-only post-sealing.

---

## 3. Canonical JSON Schema (`session_<session_id>.json`) — Schema 2.0.0

Below is the updated, canonical JSON schema specification for Version 2 Session Bundles supporting **Multi-Finding Audit Sessions (`findings: list[Finding]`)**:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SessionBundle",
  "type": "object",
  "required": [
    "schema_version",
    "scanner_version",
    "session_id",
    "build_id",
    "domain",
    "timestamp",
    "findings",
    "commercial",
    "checksum"
  ],
  "properties": {
    "schema_version": { "type": "string", "const": "2.0.0" },
    "scanner_version": { "type": "string", "example": "2.3.1" },
    "session_id": { "type": "string", "format": "uuid" },
    "build_id": { "type": "string", "format": "uuid" },
    "domain": { "type": "string", "example": "toms.com" },
    "timestamp": { "type": "string", "format": "date-time" },

    "findings": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/Finding" }
    },

    "commercial": {
      "type": "object",
      "required": [
        "est_monthly_traffic",
        "oos_frequency_pct",
        "variants_inspected",
        "variants_oos",
        "est_monthly_loss_usd",
        "lead_priority",
        "confidence_score"
      ],
      "properties": {
        "est_monthly_traffic": { "type": "integer", "minimum": 0 },
        "oos_frequency_pct": { "type": "number", "minimum": 0.0, "maximum": 100.0 },
        "variants_inspected": { "type": "integer", "minimum": 0 },
        "variants_oos": { "type": "integer", "minimum": 0 },
        "est_monthly_loss_usd": { "type": "number", "minimum": 0.0 },
        "lead_priority": { "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"] },
        "confidence_score": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
      }
    },

    "checksum": { "type": "string", "pattern": "^[a-fA-F0-9]{64}$" }
  },

  "$defs": {
    "Finding": {
      "type": "object",
      "required": [
        "finding_id",
        "product_name",
        "product_url",
        "scanned_variant",
        "out_of_stock",
        "notify_button_detected",
        "sold_out_detected",
        "review_widget_detected",
        "review_platform",
        "review_count",
        "upsell_detected",
        "sticky_atc_detected",
        "evidence",
        "bounding_boxes"
      ],
      "properties": {
        "finding_id": { "type": "string", "format": "uuid" },
        "product_name": { "type": "string" },
        "product_url": { "type": "string", "format": "uri" },
        "scanned_variant": { "type": "string" },
        "out_of_stock": { "type": "boolean" },
        "notify_button_detected": { "type": "boolean" },
        "sold_out_detected": { "type": "boolean" },
        "review_widget_detected": { "type": "boolean" },
        "review_platform": { "type": "string" },
        "review_count": { "type": "integer", "minimum": 0 },
        "upsell_detected": { "type": "boolean" },
        "sticky_atc_detected": { "type": "boolean" },
        "evidence": { "$ref": "#/$defs/VisualEvidence" },
        "bounding_boxes": { "$ref": "#/$defs/BoundingBoxMap" }
      }
    },

    "VisualEvidence": {
      "type": "object",
      "required": [
        "image_file",
        "relative_path",
        "width",
        "height",
        "sha256_hash",
        "capture_duration_ms",
        "browser_version",
        "viewport",
        "valid",
        "validation_reason"
      ],
      "properties": {
        "image_file": { "type": "string" },
        "relative_path": { "type": "string" },
        "width": { "type": "integer", "minimum": 1024 },
        "height": { "type": "integer", "minimum": 600 },
        "sha256_hash": { "type": "string", "pattern": "^[a-fA-F0-9]{64}$" },
        "capture_duration_ms": { "type": "integer", "minimum": 1 },
        "browser_version": { "type": "string" },
        "viewport": { "type": "string", "example": "1365x900" },
        "valid": { "type": "boolean" },
        "validation_reason": { "type": "string" }
      }
    },

    "BoundingBoxMap": {
      "type": "object",
      "properties": {
        "buy_box": { "$ref": "#/$defs/BoundingBox" },
        "cta": { "$ref": "#/$defs/BoundingBox" },
        "notify": { "$ref": "#/$defs/BoundingBox" },
        "reviews": { "$ref": "#/$defs/BoundingBox" },
        "upsell": { "$ref": "#/$defs/BoundingBox" },
        "sticky_atc": { "$ref": "#/$defs/BoundingBox" }
      }
    },

    "BoundingBox": {
      "type": "object",
      "required": ["x", "y", "width", "height"],
      "properties": {
        "x": { "type": "number", "minimum": 0.0 },
        "y": { "type": "number", "minimum": 0.0 },
        "width": { "type": "number", "minimum": 0.0 },
        "height": { "type": "number", "minimum": 0.0 }
      }
    }
  }
}
```

---

## 4. SHA-256 Checksum Sealing Specification

To ensure unassailable evidence integrity and prevent post-capture tampering, every `SessionBundle` is cryptographically sealed during serialization:

```
+-----------------------------------------------------------------------------------+
|                        CHECKSUM SEALING ALGORITHM MATRIX                          |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  1. Read Primary PNG Image Bytes  ──► Hash_1 = SHA256(png_bytes)                  |
|  2. Serialize Canonical JSON       ──► Hash_2 = SHA256(Canonical_JSON_Payload)     |
|     (EXCLUDING "checksum" field)                                                  |
|  3. Combine Raw 32-Byte Hash Digests ──► Sealed_Checksum = SHA256(Hash_1 + Hash_2)  |
|  4. Write Sealed Checksum File    ──► Saved to session_<session_id>.checksum     |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

### Verification Gate at Read Time:
Before any Downstream Driver (PDF, Teaser, HTML) processes a `SessionBundle`, it calls `VisualVerifier.verify_bundle_checksum(bundle_path)`:
* Extract `Hash_1` from screenshot PNG file.
* Extract JSON payload excluding `checksum` field and calculate `Hash_2` via Canonical JSON bytes.
* Combine `SHA256(Hash_1 + Hash_2)` and assert equality with `.checksum` file and `SessionBundle.checksum`.
* If mismatch detected ➔ Throw `EvidenceTamperedException` and abort execution immediately.

---

## 5. Architectural Decision Records (ADRs)

### ADR-EP-001: Multi-Finding Session Bundle Hierarchy (`findings: list[Finding]`)
* **Status:** Accepted (Locked)
* **Context:** `07_EvidencePackage.md` previously specified a single `findings` object, conflicting with `10_ModuleResponsibilities.md` Lock 3 (`SessionBundle` holds 1 to N store audit findings).
* **Decision:** `SessionBundle` schema is locked to `findings: list[Finding]`. Each `Finding` encapsulates its own PDP product findings, `VisualEvidence`, and `BoundingBoxMap`.
* **Consequences:** Store-level metadata (`domain`, `commercial`, `session_id`, `build_id`) is not duplicated per product finding. Downstream drivers can process single-finding teasers or multi-finding audit reports.
