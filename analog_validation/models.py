"""Typed boundary models; runtime checks also apply to direct Python callers."""

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Literal

Body = Literal["moon", "mars"]
Status = Literal["supported_by_literature", "model_predicted", "potential_conflict",
                 "insufficient_evidence", "requires_review", "not_applicable"]


def finite(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Expected a finite number")


@dataclass(frozen=True)
class Feature:
    value: float | None
    unit: str | None = None
    uncertainty: float | None = None  # symmetric absolute bound, NOT a confidence interval
    source: str = ""
    resolution_m: float | None = None
    period: str = ""
    quality: str = ""
    limitations: str = ""

    def __post_init__(self) -> None:
        for value in (self.value, self.uncertainty, self.resolution_m):
            if value is not None:
                finite(value)
        if self.uncertainty is not None and self.uncertainty < 0:
            raise ValueError("Uncertainty cannot be negative")
        if self.resolution_m is not None and self.resolution_m <= 0:
            raise ValueError("Resolution must be positive")


@dataclass(frozen=True)
class Constraint:
    id: str
    feature: str
    limit: float
    unit: str
    direction: Literal["max", "min"]
    source: str
    hard: bool = True
    domain: Literal["earth", "target"] = "earth"

    def __post_init__(self) -> None:
        finite(self.limit)
        if not self.id or not self.source or not self.unit:
            raise ValueError("A constraint needs an ID, unit and mission reference")
        if self.direction not in ("max", "min") or self.domain not in ("earth", "target"):
            raise ValueError("Invalid constraint direction or domain")


@dataclass(frozen=True)
class Mission:
    id: str
    objectives: tuple[str, ...]
    constraints: tuple[Constraint, ...] = ()
    equipment: dict[str, Any] = field(default_factory=dict)
    required_resolution_m: float | None = None
    purpose: Literal["nominal", "stress_test"] = "nominal"
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.id or not self.objectives or not self.version:
            raise ValueError("Mission ID, objectives and version are required")
        if self.purpose not in ("nominal", "stress_test"):
            raise ValueError("Invalid mission purpose")
        if len({c.id for c in self.constraints}) != len(self.constraints):
            raise ValueError("Duplicate mission constraint IDs")
        if self.required_resolution_m is not None:
            finite(self.required_resolution_m)
            if self.required_resolution_m <= 0:
                raise ValueError("Required resolution must be positive")


@dataclass(frozen=True)
class ValidationRequest:
    site_id: str
    geometry: dict[str, Any]
    target_id: str
    body: Body
    missions: tuple[Mission, ...]
    original_similarity: float | None
    earth_features: dict[str, Feature]
    target_features: dict[str, Feature] = field(default_factory=dict)
    feature_contributions: dict[str, float] = field(default_factory=dict)
    correlations: tuple[dict[str, Any], ...] = ()
    original_payload: dict[str, Any] = field(default_factory=dict)
    upstream_version: str = "unspecified"
    target_conditions: tuple[str, ...] = ()
    query: str = ""

    def __post_init__(self) -> None:
        if self.body not in ("moon", "mars") or not self.site_id or not self.target_id:
            raise ValueError("Site, target and moon/mars body are required")
        if not self.missions or len({m.id for m in self.missions}) != len(self.missions):
            raise ValueError("Supply nonempty, unique missions")
        if self.original_similarity is not None:
            finite(self.original_similarity)  # score scale is deliberately upstream-owned
        if not isinstance(self.query, str) or not self.query.strip() or len(self.query) > 1500:
            raise ValueError("Supply a nonempty mission search query of at most 1500 characters")


@dataclass(frozen=True)
class SimulationRecommendation:
    method: str
    required_parameters: tuple[str, ...]
    equipment: tuple[str, ...]
    measurable_outputs: tuple[str, ...]
    success_criteria: str
    residual_gap: str
    basis: str = "proposed_experiment"
    already_reproduced_conditions: tuple[str, ...] = ()
    artificially_simulatable_conditions: tuple[str, ...] = ()
    partially_simulatable_conditions: tuple[str, ...] = ()
    not_reproduced_conditions: tuple[str, ...] = ("planetary gravity",)


@dataclass(frozen=True)
class SearchEvidence:
    id: str
    title: str
    source_url: str
    snippet: str
    position: int
    query: str
    retrieved_at: str
    verification_status: str = "pending_review"


@dataclass(frozen=True)
class RecalculationResult:
    tool: str
    status: Status
    outcome: Literal["pass", "fail", "unknown"]
    value: float | None
    unit: str
    margin_bounds: tuple[float, float] | None
    assumptions: tuple[str, ...]
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConflictFinding:
    id: str
    mission_id: str
    body: Body
    category: str
    path: Literal["quantitative", "qualitative", "review"]
    status: Status
    claim: str
    mechanism: str
    applicability: str
    sources: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    required_inputs: tuple[str, ...]
    limitations: str
    impact: str
    action: str
    calculation: RecalculationResult | None = None
    simulation: SimulationRecommendation | None = None
    hard_violation: bool = False


@dataclass(frozen=True)
class RankingAdjustment:
    policy: str
    reason: str
    rank_before: int
    rank_after: int
    sensitivity: str


@dataclass
class MissionValidationResult:
    site_id: str
    mission_id: str
    original_similarity: float | None
    analog_fidelity_adjustment: float | None
    mission_suitability: float | None
    stress_test_value: float | None
    status: Status
    eligibility: str
    findings: list[ConflictFinding]
    missing_data: list[str]
    ranking: RankingAdjustment | None = None
    score_reason: str = "No calibrated scientific score transformation is available."
    feedback_actions: tuple[str, ...] = ("preference", "site_evaluation", "scientific_correction", "test_outcome")


@dataclass(frozen=True)
class UserFeedback:
    run_id: str
    site_id: str
    mission_id: str
    user_id: str
    category: str
    details: str
    evidence: tuple[str, ...] = ()
    test_conditions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category not in ("preference", "site_evaluation", "scientific_correction", "test_outcome"):
            raise ValueError("Unknown feedback category")
        if not all((self.run_id, self.site_id, self.mission_id, self.user_id, self.details)):
            raise ValueError("Feedback identifiers and details are required")
