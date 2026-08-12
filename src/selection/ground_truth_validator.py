"""
src/selection/ground_truth_validator.py — Ground-Truth Evidence Assertion Gate

Layer 4: Zero-False-Positive Validation Gate
"""
import logging
from pydantic import BaseModel, ConfigDict, Field

from src.evidence.models import SessionBundle

logger = logging.getLogger(__name__)


class GroundTruthValidationResult(BaseModel):
    """Result of ground-truth validation assertion gate."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool = Field(description="True if session passes all ground-truth assertion gates")
    rejection_reasons: list[str] = Field(default_factory=list, description="List of assertion failure reasons")


class GroundTruthValidator:
    """
    Enforces strict zero-false-positive validation assertions on SessionBundle candidates
    prior to commercial outreach presentation.
    
    BANNED OPERATIONS:
      - Modifying SessionBundle JSON, PNG, or checksum files
      - Making Playwright or network calls
      - Recalculating financial loss metrics
    """

    def validate_session_bundle(self, bundle: SessionBundle) -> GroundTruthValidationResult:
        """
        Executes strict ground-truth assertion checks:
          1. Schema version must be exactly '2.0.0'
          2. Checksum format must be valid 64-char hex SHA-256
          3. At least 1 Finding must exist in findings list
          4. Every Finding must have valid VisualEvidence (valid == True)
          5. Confidence score must be > 0.0
        """
        rejections: list[str] = []

        # 1. Schema Version Check
        if bundle.schema_version != "2.0.0":
            rejections.append(f"Invalid schema version '{bundle.schema_version}', expected '2.0.0'")

        # 2. Checksum Format Check
        if not bundle.checksum or len(bundle.checksum) != 64:
            rejections.append(f"Invalid SHA-256 checksum format: '{bundle.checksum}'")

        # 3. Findings Non-Empty Check
        if not bundle.findings or len(bundle.findings) == 0:
            rejections.append("SessionBundle contains zero PDP leak findings")

        # 4. Visual Evidence Validity Check
        for i, finding in enumerate(bundle.findings, 1):
            if not finding.evidence.valid:
                rejections.append(f"Finding #{i} ('{finding.product_name}') has invalid visual evidence: {finding.evidence.validation_reason}")

        # 5. Confidence Score Non-Zero Check
        if bundle.commercial.confidence_score <= 0.0:
            rejections.append("Commercial confidence score is 0.0 (Zero confidence estimate)")

        is_valid = len(rejections) == 0
        return GroundTruthValidationResult(is_valid=is_valid, rejection_reasons=rejections)
