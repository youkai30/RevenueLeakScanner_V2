"""
src/ingestion/tenant_config.py — Agency White-Label Tenant Configuration Model

Layer 1: Ingestion & White-Label Agency Settings
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenantConfig(BaseModel):
    """
    Immutable DTO representing white-label agency branding parameters.
    Owner: src/ingestion/tenant_config.py
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    agency_name: str = Field(default="CRO Growth Agency", description="Agency commercial brand name")
    logo_url: str = Field(default="https://assets.agency.com/logo.png", description="Agency brand logo URL")
    primary_color_hex: str = Field(default="#1E293B", description="Primary brand accent color (Hex format)")
    secondary_color_hex: str = Field(default="#0F172A", description="Secondary brand accent color (Hex format)")
    sdr_booking_link: str = Field(default="https://cal.com/agency-cro/audit", description="SDR call booking URL")
    contact_email: str = Field(default="audit@agency.com", description="Agency SDR contact email")
    store_max_runtime_seconds: int = Field(default=180, ge=1, description="Max wall-clock seconds allowed per store scan")



    @field_validator("primary_color_hex", "secondary_color_hex", mode="before")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        val = (v or "").strip()
        if not val.startswith("#") or len(val) not in (4, 7):
            raise ValueError(f"Invalid Hex color code: '{v}'. Must start with '#' (e.g. #1E293B)")
        return val.upper()
