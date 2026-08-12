"""
src/scanner/detection_state.py — Canonical Detection State Model & Failure Taxonomy

Layer 2: Mandatory 3-State Detection Architecture (CONTRACT-STATE-001)
"""
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class DetectionState(str, Enum):
    """
    Canonical 3-State Detection Model required by CONTRACT-STATE-001.
    Strictly forbids binary True/False collapse where selector missing = feature absent.
    """
    TRUE = "TRUE"        # Confirmed presence with valid positive evidence
    FALSE = "FALSE"      # Confirmed absence after sufficient valid inspection
    UNKNOWN = "UNKNOWN"  # Inconclusive, uninspected, or missing evidence (NEVER generates an opportunity)


class DetectionFailureReason(str, Enum):
    """
    Failure taxonomy categorizing WHY a detector produced UNKNOWN or FALSE.
    """
    FEATURE_ABSENT = "FEATURE_ABSENT"              # Validated evidence proves feature is absent -> FALSE
    SELECTOR_NOT_FOUND = "SELECTOR_NOT_FOUND"      # Selectors missing; insufficient for absence -> UNKNOWN
    DOM_UNAVAILABLE = "DOM_UNAVAILABLE"            # DOM container destroyed or unreachable -> UNKNOWN
    PAGE_INCOMPLETE = "PAGE_INCOMPLETE"            # DOM load incomplete or lazy elements pending -> UNKNOWN
    INTERACTION_FAILED = "INTERACTION_FAILED"      # Click or scroll verification failed -> UNKNOWN
    TIMEOUT = "TIMEOUT"                            # Navigation or evaluation timed out -> UNKNOWN
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"  # Inconsistent DOM signals detected -> UNKNOWN
    UNSUPPORTED_STRUCTURE = "UNSUPPORTED_STRUCTURE"# Custom/enterprise app DOM structure -> UNKNOWN
    INVALID_PAGE_STATE = "INVALID_PAGE_STATE"      # Non-REAL_PRODUCT page -> UNKNOWN
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"# Generic insufficient evidence fallback -> UNKNOWN


class DetectionResult(BaseModel):
    """
    Canonical Detection DTO returned by all scanner detection engines.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: DetectionState = Field(description="Canonical 3-state detection result")
    reason: DetectionFailureReason = Field(description="Structured reason classification")
    details: str = Field(default="", description="Machine-readable explanation or platform name")
    count: int = Field(default=0, ge=0, description="Extracted count if applicable")
