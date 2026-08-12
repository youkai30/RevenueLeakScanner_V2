"""
src/presentation/models.py — Presentation Payload DTO Contracts

Layer 5: Presentation & Deliverable DTOs
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class CalloutTag(BaseModel):
    """Callout tag directive for overlaying visual cues over evidence."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(description="Display text of callout tag")
    target_element: str = Field(description="Target bounding box element key (buy_box, cta, notify)")
    color_theme: str = Field(default="red", description="Tag color theme (red, green, orange)")


class FindingPresentation(BaseModel):
    """Presentation formatting for a single PDP finding."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(description="String representation of finding UUID")
    product_name: str = Field(description="Display title of product")
    product_url: str = Field(description="Full PDP URL")
    scanned_variant: str = Field(description="Inspected variant description")
    out_of_stock: bool = Field(description="OOS status")
    notify_button_detected: bool = Field(description="BIS alert status")
    review_widget_detected: bool = Field(description="Review widget status")
    review_platform: str = Field(description="Review platform name")
    review_count: int = Field(description="Extracted review count")
    evidence_image_file: str = Field(description="Base PNG filename")
    callout_tags: list[CalloutTag] = Field(default_factory=list, description="Overlay callouts")


class PDFPayload(BaseModel):
    """
    Immutable DTO for 1-Page Executive PDF rendering.
    Preserves multi-finding hierarchy and commercial disclosure.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(description="Target store domain")
    session_id: str = Field(description="Session UUID string")
    build_id: str = Field(description="Build UUID string")
    timestamp: str = Field(description="Audit UTC timestamp string")
    schema_version: str = Field(description="Schema version string")
    
    # Financial Commercial Summary
    est_monthly_loss_usd: float = Field(description="Calculated monthly lost revenue $")
    lead_priority: str = Field(description="Lead priority rating (HIGH, MEDIUM, LOW)")
    confidence_score: float = Field(description="Data confidence decimal [0.0, 1.0]")
    est_monthly_traffic: int = Field(description="Inspected traffic visits")
    oos_frequency_pct: float = Field(description="Inspected sample OOS %")
    variants_inspected: int = Field(description="Inspected sample variant count")
    variants_oos: int = Field(description="Inspected sample OOS count")
    baseline_cr_pct: float = Field(description="Baseline CR percentage (e.g. 2.0%)")
    aov_usd: float = Field(description="Average Order Value USD used")
    footnote_disclosure: str = Field(description="Mandatory fallback disclosure footnote statement")
    
    # White-Label Agency Branding
    agency_name: str = Field(description="Agency white-label brand name")
    agency_logo_url: str = Field(description="Agency logo image URL")
    primary_color_hex: str = Field(description="Primary brand accent color hex")
    sdr_booking_link: str = Field(description="SDR call booking URL")
    
    # Findings Hierarchy
    findings: list[FindingPresentation] = Field(min_length=1, description="List of PDP findings")


class EmailPayload(BaseModel):
    """Immutable DTO for SDR cold outreach teaser email generation."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(description="Target store domain")
    session_id: str = Field(description="Session UUID string")
    est_monthly_loss_usd: float = Field(description="Estimated monthly loss USD")
    headline_finding: FindingPresentation = Field(description="Primary PDP finding for cold email hook")
    teaser_image_file: str = Field(description="Cropped teaser image filename")
    sdr_booking_link: str = Field(description="SDR booking URL")
