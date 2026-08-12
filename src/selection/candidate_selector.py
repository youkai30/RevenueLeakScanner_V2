"""
src/selection/candidate_selector.py — Session Bundle Candidate Discovery Engine

Layer 4: Selection Layer Candidate Selector
"""
import logging
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

from src.config import SESSIONS_DIR
from src.evidence.models import SessionBundle
from src.evidence.session_storage import SessionStorage
from src.selection.evidence_scorer import EvidenceScorer
from src.selection.ground_truth_validator import GroundTruthValidator

logger = logging.getLogger(__name__)


class ScoredCandidate(BaseModel):
    """Container for a scored and validated SessionBundle candidate."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_bundle: SessionBundle = Field(description="Validated SessionBundle DTO")
    score: float = Field(ge=0.0, le=100.0, description="Computed evidence rank score")
    is_valid_ground_truth: bool = Field(description="Ground-truth validation status")


class CandidateSelector:
    """
    Globs persisted session bundle directories in storage/sessions/, reads them read-only
    via SessionStorage, runs GroundTruthValidator assertions, and ranks top scoring candidates.
    """

    def __init__(
        self,
        storage: SessionStorage | None = None,
        validator: GroundTruthValidator | None = None,
        scorer: EvidenceScorer | None = None,
    ) -> None:
        self.storage = storage or SessionStorage()
        self.validator = validator or GroundTruthValidator()
        self.scorer = scorer or EvidenceScorer()

    def discover_and_rank_candidates(
        self,
        domain: str | None = None,
        min_score: float = 0.0,
    ) -> list[ScoredCandidate]:
        """
        Globs storage/sessions/ directories, validates ground truth, computes rank scores,
        and returns list of ScoredCandidate objects sorted descending by score.
        """
        candidates: list[ScoredCandidate] = []
        base_dir = self.storage.base_dir

        if not base_dir.exists():
            return candidates

        # Determine target domain directories
        if domain:
            domain_dirs = [base_dir / domain] if (base_dir / domain).exists() else []
        else:
            domain_dirs = [d for d in base_dir.iterdir() if d.is_dir()]

        for d_dir in domain_dirs:
            target_domain = d_dir.name
            for s_dir in d_dir.iterdir():
                if s_dir.is_dir() and not s_dir.name.startswith("temp_"):
                    session_id = s_dir.name
                    try:
                        bundle = self.storage.get_bundle(target_domain, session_id)
                        val_res = self.validator.validate_session_bundle(bundle)

                        if val_res.is_valid:
                            score = self.scorer.calculate_score(bundle)
                            if score >= min_score:
                                candidates.append(
                                    ScoredCandidate(
                                        session_bundle=bundle,
                                        score=score,
                                        is_valid_ground_truth=True,
                                    )
                                )
                    except Exception as exc:
                        logger.debug("Failed to load/validate candidate session '%s': %s", session_id, exc)
                        continue

        # Sort candidates descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates
