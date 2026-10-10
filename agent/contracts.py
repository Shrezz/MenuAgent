"""Integration boundary for the future worker and planning agent."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class PlanningRequest:
    household_id: str
    week_start: str
    snapshot_id: str
    locked_slot_ids: tuple[str, ...] = ()
    max_revisions: int = 5


@dataclass(frozen=True)
class PlanningIssue:
    code: str
    message: str
    severity: Literal["required", "recommendation", "missing_data"]
    affected_slot_ids: tuple[str, ...] = ()


@dataclass
class PlanningResult:
    status: Literal["draft_ready", "needs_input", "failed", "cancelled"]
    job_id: str
    plan_version_id: str | None = None
    issues: list[PlanningIssue] = field(default_factory=list)
