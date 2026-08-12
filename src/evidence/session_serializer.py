"""
src/evidence/session_serializer.py — Evidence & Session Bundle Serializer Engine

Layer 3: Evidence Builder & Session Storage Compiler
"""
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import UUID, uuid4

from src.config import SCANNER_VERSION, SCHEMA_VERSION
from src.evidence.canonical_json import dumps_canonical
from src.evidence.checksum import calculate_sealed_checksum
from src.evidence.models import (
    BoundingBoxMap,
    CommercialImpact,
    Finding,
    SessionBundle,
    VisualEvidence,
)
from src.evidence.session_storage import SessionStorage
from src.evidence.visual_verifier import VisualVerifier
from src.exceptions import (
    EvidenceTamperedException,
    InvalidBundleException,
    SessionExistsException,
)
from src.scanner.models import PDPScanResult, TransientScanContext

logger = logging.getLogger(__name__)


class EvidenceBuilder:
    """
    Compiles verified evidence + transient findings + commercial calculation result into an immutable SessionBundle,
    and persists it using Write-Once SessionStorage.
    """

    def __init__(self, storage: SessionStorage | None = None) -> None:
        self.storage = storage or SessionStorage()
        self.verifier = VisualVerifier()

    def build_finding(
        self,
        pdp_result: PDPScanResult,
        png_bytes: bytes,
        bounding_boxes: BoundingBoxMap,
        session_id: UUID,
        browser_version: str = "Chromium 120.0",
        viewport: str = "1365x900",
    ) -> tuple[Finding, str, int, int, str]:
        """
        Validates PNG bytes via VisualVerifier and constructs a strongly-typed Finding DTO.
        Returns tuple of (Finding, png_sha256_hash, width, height, relative_png_path).
        """
        valid, reason, width, height, sha256_hash = self.verifier.verify_png_bytes(png_bytes)

        if not valid:
            raise InvalidBundleException(f"Visual evidence verification failed for finding '{pdp_result.product_name}': {reason}")

        session_str = str(session_id)
        finding_uuid = uuid4()
        evidence_uuid = uuid4()
        png_filename = f"session_{session_str}_{evidence_uuid}.png"
        parsed_url = urlparse(pdp_result.product_url)
        relative_path = f"{parsed_url.netloc}/{session_str}/{png_filename}"

        visual_evidence = VisualEvidence(
            image_file=png_filename,
            relative_path=relative_path,
            width=width,
            height=height,
            sha256_hash=sha256_hash,
            capture_duration_ms=450,
            browser_version=browser_version,
            viewport=viewport,
            valid=(
                not getattr(pdp_result, "has_unresolved_modal", False)
                and getattr(pdp_result, "product_identity_visible", True)
                and getattr(pdp_result, "buy_box_visible", True)
                and getattr(pdp_result, "relevant_social_proof_region_visible", True)
                and getattr(pdp_result, "relevant_upsell_region_visible", True)
            ),
            validation_reason=(
                "Unresolved modal overlay blocking the page view" if getattr(pdp_result, "has_unresolved_modal", False)
                else "Product identity not visible in screenshot" if not getattr(pdp_result, "product_identity_visible", True)
                else "Product buy box not visible in screenshot" if not getattr(pdp_result, "buy_box_visible", True)
                else "Relevant social proof region not visible in screenshot" if not getattr(pdp_result, "relevant_social_proof_region_visible", True)
                else "Relevant upsell region not visible in screenshot" if not getattr(pdp_result, "relevant_upsell_region_visible", True)
                else reason
            ),
            scroll_y=getattr(pdp_result, "scroll_y", 0),
            store_domain=parsed_url.netloc,
            pdp_url=pdp_result.product_url,
            finding_id=str(finding_uuid),
            evidence_id=str(evidence_uuid),
        )

        finding = Finding(
            finding_id=finding_uuid,
            product_name=pdp_result.product_name,
            product_url=pdp_result.product_url,
            scanned_variant=pdp_result.scanned_variant,
            out_of_stock=pdp_result.out_of_stock,
            notify_button_detected=pdp_result.notify_button_detected,
            sold_out_detected=pdp_result.sold_out_detected,
            review_widget_detected=pdp_result.review_widget_detected,
            review_platform=pdp_result.review_platform,
            review_count=pdp_result.review_count,
            upsell_detected=pdp_result.upsell_detected,
            sticky_atc_detected=pdp_result.sticky_atc_detected,
            page_state=str(getattr(pdp_result.page_state, "value", pdp_result.page_state) if getattr(pdp_result, "page_state", None) else ""),
            opportunities=[opp.model_dump(mode="json") if hasattr(opp, "model_dump") else opp for opp in pdp_result.opportunities],
            evidence=visual_evidence,
            bounding_boxes=bounding_boxes,
            bis_detection_state=getattr(pdp_result, "bis_detection_state", "UNKNOWN"),
            review_detection_state=getattr(pdp_result, "review_detection_state", "UNKNOWN"),
            upsell_detection_state=getattr(pdp_result, "upsell_detection_state", "UNKNOWN"),
            sticky_atc_detection_state=getattr(pdp_result, "sticky_atc_detection_state", "UNKNOWN"),
        )

        return finding, sha256_hash, width, height, relative_path



    def compile_and_save_session(
        self,
        domain: str,
        transient_context: TransientScanContext,
        commercial_impact: CommercialImpact,
        pdp_evidence_items: list[tuple[PDPScanResult, bytes, BoundingBoxMap]],
        session_id: UUID | None = None,
        build_id: UUID | None = None,
        viewport: str = "1365x900",
    ) -> SessionBundle:
        """
        Compiles transient scan context + commercial impact + per-finding verified evidence into an immutable SessionBundle,
        seals with SHA-256 checksum, and persists via Write-Once SessionStorage.
        
        pdp_evidence_items is a list of (pdp_result, png_bytes, bounding_boxes) tuples, ensuring EACH Finding
        anchors its own verified screenshot PNG and spatial bounding boxes.
        """
        current_session_id = session_id or uuid4()
        current_build_id = build_id or uuid4()
        timestamp_str = datetime.now(timezone.utc).isoformat()

        findings_list: list[Finding] = []
        primary_png_bytes: bytes | None = None
        all_pngs: dict[str, bytes] = {}

        if pdp_evidence_items:
            for pdp, png_bytes, boxes in pdp_evidence_items:
                if primary_png_bytes is None:
                    primary_png_bytes = png_bytes

                finding_obj, _, _, _, _ = self.build_finding(
                    pdp_result=pdp,
                    png_bytes=png_bytes,
                    bounding_boxes=boxes,
                    session_id=current_session_id,
                    viewport=viewport,
                )
                findings_list.append(finding_obj)
                all_pngs[finding_obj.evidence.image_file] = png_bytes
        elif transient_context.pdp_results:
            # Legacy fallback if no pdp_evidence_items provided
            for pdp in transient_context.pdp_results:
                dummy_bytes = b"FALLBACK"
                if primary_png_bytes is None:
                    primary_png_bytes = dummy_bytes
                finding_obj, _, _, _, _ = self.build_finding(
                    pdp_result=pdp,
                    png_bytes=dummy_bytes,
                    bounding_boxes=BoundingBoxMap(),
                    session_id=current_session_id,
                    viewport=viewport,
                )
                findings_list.append(finding_obj)
                all_pngs[finding_obj.evidence.image_file] = dummy_bytes

        if not primary_png_bytes:
            raise InvalidBundleException("At least one valid evidence PNG stream is required for session bundle compilation.")

        # Convert Findings list and CommercialImpact DTO to dictionary payload for checksum sealing
        findings_json_dicts = [f.model_dump(mode="json") for f in findings_list]
        commercial_json_dict = commercial_impact.model_dump(mode="json")

        contact_info_dict = transient_context.metadata.get("contact_info", {})
        bundle_payload_dict = {
            "schema_version": SCHEMA_VERSION,
            "scanner_version": SCANNER_VERSION,
            "session_id": str(current_session_id),
            "build_id": str(current_build_id),
            "domain": domain,
            "timestamp": timestamp_str,
            "findings": findings_json_dicts,
            "commercial": commercial_json_dict,
            "contact_info": contact_info_dict,
        }

        # Persist atomically via Write-Once SessionStorage
        import inspect
        sig = inspect.signature(self.storage.save_new_bundle)
        if "all_pngs" in sig.parameters:
            session_bundle = self.storage.save_new_bundle(
                domain=domain,
                session_id=current_session_id,
                png_bytes=primary_png_bytes,
                session_bundle_dict=bundle_payload_dict,
                all_pngs=all_pngs,
            )
        else:
            session_bundle = self.storage.save_new_bundle(
                domain=domain,
                session_id=current_session_id,
                png_bytes=primary_png_bytes,
                session_bundle_dict=bundle_payload_dict,
            )

        return session_bundle
