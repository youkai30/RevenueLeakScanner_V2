"""
src/orchestration/models.py — Production Orchestration DTOs & Batch Results

Layer 6: Production Batch Execution & Worker Models
"""
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class StoreExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


class StoreExecutionResult(BaseModel):
    """
    Serializable execution result returned by an isolated worker process.
    MUST NOT contain live Playwright objects (Page, Browser, Context).
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(description="Target store domain name")
    status: StoreExecutionStatus = Field(description="Store execution status (SUCCESS, FAILED, SKIPPED)")
    session_id: str | None = Field(default=None, description="UUID session identifier if successful")
    build_id: str | None = Field(default=None, description="UUID batch build identifier")
    duration_ms: int = Field(ge=0, description="Execution duration in milliseconds")
    error_type: str | None = Field(default=None, description="Exception class name if failed")
    error_message: str | None = Field(default=None, description="Error message if failed")
    session_json_path: str | None = Field(default=None, description="Path to persisted session.json")
    pdf_report_path: str | None = Field(default=None, description="Path to generated audit.pdf")
    teaser_image_path: str | None = Field(default=None, description="Path to generated teaser.png")
    est_monthly_loss_usd: float | None = Field(default=None, description="Calculated lost revenue USD")
    lead_priority: str | None = Field(default=None, description="Agency lead priority (HIGH, MEDIUM, LOW)")
    store_timeout: bool = Field(default=False, description="Whether store exceeded hard wall-clock time budget")
    store_timeout_seconds: int | None = Field(default=None, description="Max allowed store runtime seconds")
    store_elapsed_seconds: float | None = Field(default=None, description="Actual elapsed store runtime seconds")
    timeout_reason: str | None = Field(default=None, description="Reason for store execution timeout")
    timeout_phase: str | None = Field(default=None, description="Scanner phase when timeout occurred")



class BatchExecutionSummary(BaseModel):
    """Machine-readable batch execution summary report."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str = Field(description="UUID batch run identifier")
    timestamp_utc: str = Field(description="ISO-8601 execution start timestamp")
    total_stores: int = Field(ge=0, description="Total candidate stores loaded")
    successful_count: int = Field(ge=0, description="Successfully processed store count")
    failed_count: int = Field(ge=0, description="Failed store count")
    skipped_count: int = Field(ge=0, description="Skipped store count")
    success_rate_pct: float = Field(ge=0.0, le=100.0, description="Success percentage")
    total_duration_ms: int = Field(ge=0, description="Total batch duration in ms")
    results: list[StoreExecutionResult] = Field(description="Detailed per-store execution results")
