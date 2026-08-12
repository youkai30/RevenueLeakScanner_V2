"""
src/commercial/models.py — Commercial Intelligence Data Contracts & Provenance Models

Layer 3 (Commercial): DTOs for Financial Estimation & Parameter Provenance
"""
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParameterSource(str, Enum):
    PRIMARY_MEASURED = "PRIMARY_MEASURED"
    FALLBACK_ASSUMED = "FALLBACK_ASSUMED"


class CommercialParameterProvenance(BaseModel):
    """Tracks parameter provenance, source type, and confidence impact."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    parameter_name: str = Field(description="Name of commercial parameter")
    value: Any = Field(description="Numerical or string value used")
    source: ParameterSource = Field(description="PRIMARY_MEASURED vs FALLBACK_ASSUMED")
    source_detail: str = Field(description="Description of exact data source or fallback tier used")
    confidence_impact: float = Field(default=0.0, description="Confidence penalty adjustment (e.g. -0.3)")


class CommercialCalculationResult(BaseModel):
    """
    Detailed internal result of Commercial Impact Engine processing,
    containing both the target CommercialImpact DTO and complete parameter provenance disclosure.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    est_monthly_traffic: int = Field(ge=0, description="Monthly traffic visits used")
    oos_frequency_pct: float = Field(ge=0.0, le=100.0, description="Inspected OOS variant ratio %")
    variants_inspected: int = Field(ge=0, description="Count of variants inspected in sample")
    variants_oos: int = Field(ge=0, description="Count of out-of-stock variants in sample")
    baseline_cr: float = Field(ge=0.0, le=1.0, description="Baseline conversion rate decimal (default 0.02)")
    aov_usd: float = Field(ge=0.0, description="Average order value in USD used")
    est_monthly_loss_usd: float = Field(ge=0.0, description="Calculated estimated monthly lost revenue USD")
    lead_priority: str = Field(description="Priority rating: HIGH, MEDIUM, or LOW")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Final clamped confidence score 0.0 to 1.0")
    has_fallback_parameters: bool = Field(description="True if any parameter used fallback assumption")
    provenance_records: list[CommercialParameterProvenance] = Field(description="Detailed provenance list")
    footnote_disclosure: str = Field(description="Commercial disclosure statement for outreach reports")
    financial_loss_status: str = Field(
        default="UNKNOWN",
        description="Financial loss status: VERIFIED, ESTIMATED, or UNKNOWN"
    )

    @field_validator("lead_priority", mode="before")
    @classmethod
    def validate_lead_priority(cls, v: str) -> str:
        if v not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"lead_priority must be HIGH, MEDIUM, or LOW, got: '{v}'")
        return v
