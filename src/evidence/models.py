"""
src/evidence/models.py — Core Evidence Domain Models & DTOs

Layer 3: Evidence & Session Artifact Contracts
"""
import re
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


from src.exceptions import (
    InvalidBoundingBoxError,
    InvalidCommercialMetricsError,
    RevenueLeakScannerError,
)


class BoundingBox(BaseModel):
    """Spatial coordinates of a DOM element."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float = Field(ge=0.0, description="X coordinate in pixels")
    y: float = Field(ge=0.0, description="Y coordinate in pixels")
    width: float = Field(ge=0.0, description="Width in pixels")
    height: float = Field(ge=0.0, description="Height in pixels")

    @field_validator("x", "y", "width", "height", mode="before")
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        if v is None or v < 0.0:
            raise InvalidBoundingBoxError(f"BoundingBox values must be non-negative, got: {v}")
        return float(v)


class BoundingBoxSignal(BaseModel):
    """Signals that contributed to a bounding box assignment, for auditability."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    cta_signal: bool = Field(default=False, description="CTA text detected (add to cart, buy now, etc.)")
    price_signal: bool = Field(default=False, description="Price element detected")
    variant_signal: bool = Field(default=False, description="Variant selector detected")
    product_form_signal: bool = Field(default=False, description="Product form detected")
    visibility_signal: bool = Field(default=False, description="Element in viewport")
    spatial_coherence: bool = Field(default=False, description="Related elements grouped together")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    reason: str = Field(default="", description="Human-readable reason for confidence")


class BoundingBoxMap(BaseModel):
    """Collection of detected spatial bounding boxes for key PDP elements."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    buy_box: BoundingBox | None = None
    buy_box_signals: BoundingBoxSignal | None = None
    cta: BoundingBox | None = None
    notify: BoundingBox | None = None
    reviews: BoundingBox | None = None
    upsell: BoundingBox | None = None
    sticky_atc: BoundingBox | None = None
    expected_social_proof_region: BoundingBox | None = None
    expected_social_proof_signals: BoundingBoxSignal | None = None


class VisualEvidence(BaseModel):
    """Visual proof screenshot metadata & stream integrity assertions."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    image_file: str = Field(description="Base filename of screenshot PNG")
    relative_path: str = Field(description="Relative path inside storage/sessions/")
    width: int = Field(ge=1024, description="Screenshot width in pixels")
    height: int = Field(ge=600, description="Screenshot height in pixels")
    sha256_hash: str = Field(description="64-character hex SHA-256 hash of PNG bytes")
    capture_duration_ms: int = Field(gt=0, description="Execution capture duration in ms")
    browser_version: str = Field(description="Playwright browser instance version")
    viewport: str = Field(default="1365x900", description="Viewport resolution string")
    valid: bool = Field(description="Visual Pillow stream & canvas verification status")
    validation_reason: str = Field(default="OK", description="Validation result explanation")
    scroll_y: int = Field(default=0, description="Actual scroll position in pixels")
    store_domain: str = Field(default="", description="Target store domain")
    pdp_url: str = Field(default="", description="Product detail page URL")
    finding_id: str = Field(default="", description="Bound Finding UUID string")
    evidence_id: str = Field(default="", description="Unique UUID for this evidence")
    finding_visually_proven: bool = Field(
        default=False,
        description="Whether screenshot independently proves the claimed finding (not DOM-detector dependent)",
    )

    @field_validator("sha256_hash", mode="before")
    @classmethod
    def validate_sha256_format(cls, v: str) -> str:
        if not isinstance(v, str) or not re.match(r"^[a-fA-F0-9]{64}$", v):
            raise RevenueLeakScannerError(f"Invalid SHA-256 hex string: '{v}'")
        return v.lower()


class Finding(BaseModel):
    """Represents one specific PDP conversion leak finding inside an audit session."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: UUID = Field(default_factory=uuid4, description="Unique UUID for this finding")
    product_name: str = Field(description="Name of inspected PDP product")
    product_url: str = Field(description="Full URL of inspected PDP product")
    scanned_variant: str = Field(description="Selected variant option string")
    out_of_stock: bool = Field(description="Is selected variant out of stock")
    notify_button_detected: bool = Field(description="Was BIS modal / alert form detected")
    sold_out_detected: bool = Field(description="Was sold-out CTA indicator detected")
    review_widget_detected: bool = Field(description="Was review widget detected")
    review_platform: str = Field(default="", description="Platform name if review widget detected")
    review_count: int = Field(ge=0, description="Extracted review count")
    upsell_detected: bool = Field(default=False, description="Was upsell module detected")
    sticky_atc_detected: bool = Field(default=False, description="Was sticky ATC detected")
    page_state: str = Field(default="", description="Validated PDP page state classification")
    bis_detection_state: str = Field(default="UNKNOWN")
    review_detection_state: str = Field(default="UNKNOWN")
    upsell_detection_state: str = Field(default="UNKNOWN")
    sticky_atc_detection_state: str = Field(default="UNKNOWN")
    
    # Independent Commercial Opportunities Collection
    opportunities: list[dict[str, Any]] = Field(default_factory=list, description="List of validated commercial opportunities detected on this PDP")

    evidence: VisualEvidence = Field(description="Visual proof PNG metadata")
    bounding_boxes: BoundingBoxMap = Field(default_factory=BoundingBoxMap, description="Spatial coordinates")
    
    # Visual proof tracking — independent of DOM detector
    product_identity_visually_proven: bool = Field(
        default=False,
        description="Whether product identity (name/title) is visibly proven in screenshot",
    )
    buy_box_visually_proven: bool = Field(
        default=False,
        description="Whether buy box is visibly proven in screenshot (not just detected)",
    )
    social_proof_region_visually_proven: bool = Field(
        default=False,
        description="Whether the finding-specific social proof region is visibly proven in screenshot",
    )
    upsell_region_visually_proven: bool = Field(
        default=False,
        description="Whether the finding-specific upsell region is visibly proven in screenshot",
    )
    sticky_atc_region_visually_proven: bool = Field(
        default=False,
        description="Whether the finding-specific sticky ATC region is visibly proven in screenshot",
    )




class CommercialImpact(BaseModel):
    """Quantified financial lost revenue metrics & priority classifications."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    est_monthly_traffic: int = Field(ge=0, description="Estimated monthly traffic visits")
    oos_frequency_pct: float = Field(ge=0.0, le=100.0, description="Inspected OOS variant ratio %")
    variants_inspected: int = Field(ge=0, description="Count of variants inspected in sample")
    variants_oos: int = Field(ge=0, description="Count of out-of-stock variants in sample")
    est_monthly_loss_usd: float = Field(ge=0.0, description="Calculated monthly lost revenue $")
    lead_priority: str = Field(description="Priority rating: HIGH, MEDIUM, or LOW")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Data estimation confidence 0.0-1.0")
    financial_loss_status: str = Field(
        default="UNKNOWN",
        description="Financial loss status: VERIFIED, ESTIMATED, or UNKNOWN"
    )

    @field_validator("lead_priority", mode="before")
    @classmethod
    def validate_lead_priority(cls, v: str) -> str:
        if v not in ("HIGH", "MEDIUM", "LOW"):
            raise InvalidCommercialMetricsError(f"lead_priority must be HIGH, MEDIUM, or LOW, got: '{v}'")
        return v

    @field_validator("confidence_score", mode="before")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        val = float(v)
        if val < 0.0 or val > 1.0:
            raise InvalidCommercialMetricsError(f"confidence_score must be between 0.0 and 1.0, got: {val}")
        return val


class SessionBundle(BaseModel):
    """
    Immutable, sealed Session Bundle representing one completed store audit run.
    Owner: src/evidence/session_serializer.py
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="2.0.0", description="Strict Schema version const")
    scanner_version: str = Field(description="Scanner engine version")
    session_id: UUID = Field(description="Unique UUIDv4 session identifier")
    build_id: UUID = Field(description="Unique UUIDv4 batch build identifier")
    domain: str = Field(description="Normalized domain hostname")
    timestamp: str = Field(description="ISO-8601 UTC execution timestamp")
    findings: list[Finding] = Field(min_length=1, description="List of PDP leak findings")
    commercial: CommercialImpact = Field(description="Financial impact metrics")
    checksum: str = Field(description="Sealed SHA-256 combined checksum signature")
    contact_info: dict[str, Any] = Field(default_factory=dict, description="Extracted contact info during scan")

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != "2.0.0":
            raise RevenueLeakScannerError(f"SessionBundle schema_version must be exactly '2.0.0', got: '{v}'")
        return v

    @field_validator("checksum", mode="before")
    @classmethod
    def validate_checksum_format(cls, v: str) -> str:
        if not isinstance(v, str) or not re.match(r"^[a-fA-F0-9]{64}$", v):
            raise RevenueLeakScannerError(f"Invalid checksum SHA-256 signature format: '{v}'")
        return v.lower()
