"""
src/scanner/models.py — Scanner Data Models & Transient ScanContext DTO
Layer 2: Scanner & DOM Inspection Models
"""
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from src.scanner.page_validator import PageState


class OpportunityType(str, Enum):
    REVENUE_LEAK = "REVENUE_LEAK"
    MISSING_SOCIAL_PROOF = "MISSING_SOCIAL_PROOF"
    MISSING_UPSELL = "MISSING_UPSELL"
    MISSING_STICKY_ATC = "MISSING_STICKY_ATC"
    NONE = "NONE"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CommercialOpportunity(BaseModel):
    """Represents a single validated commercial opportunity on a PDP with structured evidence status."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    opportunity_type: OpportunityType = Field(description="Evaluated commercial opportunity classification")
    commercial_problem_summary: str = Field(description="Description of detected commercial problem")
    sellable_service_angle: str = Field(description="Agency service angle")
    is_valid_opportunity: bool = Field(default=True, description="True if a genuine sellable commercial opportunity is proven")
    evidence_status: EvidenceStatus = Field(default=EvidenceStatus.VERIFIED, description="Structured evidence verification protocol classification")
    inspected_surfaces: list[str] = Field(default_factory=list, description="List of purchase-surface locations inspected")


class VariantInfo(BaseModel):
    """Structured result of a single variant option inspection."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku_name: str = Field(description="Variant option name/title (e.g. 'Size 8.5 / Navy Mesh')")
    variant_id: str = Field(default="", description="Canonical Shopify Variant ID or SKU code")
    option_type: str = Field(default="Size", description="Option type classification")
    is_available: bool = Field(description="Is variant available for purchase")
    price_usd: float = Field(default=0.0, ge=0.0, description="Variant price in USD")


class PDPScanResult(BaseModel):
    """Structured result for a single inspected Product Detail Page."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    product_name: str = Field(description="Scraped product title")
    product_url: str = Field(description="Inspected PDP URL")
    scanned_variant: str = Field(description="Target selected variant option string")
    scanned_variant_id: str = Field(default="", description="Canonical platform Variant ID / SKU identity")
    out_of_stock: bool = Field(description="Is target variant out of stock")
    notify_button_detected: bool = Field(description="Was Back-In-Stock alert modal detected")
    sold_out_detected: bool = Field(description="Was sold-out CTA indicator detected")
    page_state: PageState = Field(description="Validated PDP page state classification (CONTRACT-PDP-001)")
    review_widget_detected: bool = Field(default=False, description="Was review widget detected")
    review_platform: str = Field(default="", description="Platform name if review widget detected")
    review_count: int = Field(default=0, ge=0, description="Extracted review count")
    upsell_detected: bool = Field(default=False, description="Was upsell module detected")
    sticky_atc_detected: bool = Field(default=False, description="Was sticky ATC detected")
    variants_inspected: int = Field(default=0, ge=0, description="Total variants inspected on page")
    variants_oos: int = Field(default=0, ge=0, description="Total out-of-stock variants found")
    scroll_y: int = Field(default=0, description="Actual scroll position in pixels when screenshot captured")

    # 1:1 Evidence Binding Artifacts (CONTRACT-EVIDENCE-001)
    png_bytes: bytes | None = Field(default=None, description="Raw PNG bytes captured immediately during PDP inspection")
    bounding_boxes: Any | None = Field(default=None, description="Spatial BoundingBoxMap captured immediately during PDP inspection")

    # Independent Commercial Opportunities Collection
    opportunities: list[CommercialOpportunity] = Field(default_factory=list, description="List of validated commercial opportunities detected on this PDP")

    inspected_prices: list[float] = Field(
        default_factory=list,
        description="Extracted variant prices"
    )

    bis_detection_state: str = Field(default="UNKNOWN")
    review_detection_state: str = Field(default="UNKNOWN")
    upsell_detection_state: str = Field(default="UNKNOWN")
    sticky_atc_detection_state: str = Field(default="UNKNOWN")

    has_unresolved_modal: bool = Field(default=False, description="Unresolved modal overlay blocking the page view")
    product_identity_visible: bool = Field(default=True, description="Is product identity visible in visual evidence")
    buy_box_visible: bool = Field(default=True, description="Is buy box visible in visual evidence")
    relevant_social_proof_region_visible: bool = Field(default=True, description="Is relevant social proof region visible in visual evidence")
    relevant_upsell_region_visible: bool = Field(default=True, description="Is relevant upsell region visible in visual evidence")

    # ─────────────────────────────────────────────────────────────
    # P1.5 — Evidence capture metadata (populated by core_scanner
    # from the EvidenceCollector instance; REAL values, no fabrication)
    # ─────────────────────────────────────────────────────────────
    capture_duration_ms: int = Field(default=0, ge=0, description="Actual screenshot capture duration in ms")
    browser_version: str = Field(default="", description="Playwright browser instance version string")

    # ─────────────────────────────────────────────────────────────
    # P1.5 — Independent visual-proof flags (fail-closed defaults).
    # True ONLY when the screenshot itself proves the region.
    # ─────────────────────────────────────────────────────────────
    product_identity_visually_proven: bool = Field(default=False, description="Product identity visibly proven in screenshot")
    buy_box_visually_proven: bool = Field(default=False, description="Buy box visibly proven in screenshot")
    social_proof_region_visually_proven: bool = Field(default=False, description="Finding-specific social proof region visibly proven")
    upsell_region_visually_proven: bool = Field(default=False, description="Finding-specific upsell region visibly proven")
    sticky_atc_region_visually_proven: bool = Field(default=False, description="Finding-specific sticky ATC region visibly proven")
    finding_visually_proven: bool = Field(default=False, description="Overall finding independently proven by the screenshot")


class TransientScanContext(BaseModel):
    """
    TRANSIENT RUNTIME STATE:
    In-memory scraping workspace passed strictly between Scanner Engine,
    Commercial Impact Engine, and Evidence Builder.
    NEVER PERSISTED TO DISK AS A STANDALONE ARTIFACT.
    """
    model_config = ConfigDict(frozen=False, extra="forbid")

    domain: str = Field(description="Target store domain")
    pdp_results: list[PDPScanResult] = Field(default_factory=list, description="Scraped PDP results")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Transient scanner execution flags")
