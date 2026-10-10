"""Finite budgets shared by model, source and application-backed tool steps."""
from dataclasses import dataclass, field
from time import monotonic


class PlanningBudgetExceeded(RuntimeError):
    pass


@dataclass
class AgentBudget:
    max_model_calls: int = 11
    max_revisions: int = 3
    max_tool_calls: int = 40
    max_external_fetches: int = 6
    max_seconds: float = 600
    started: float = field(default_factory=monotonic)
    model_calls: int = 0
    tool_calls: int = 0
    external_fetches: int = 0

    def step(self, kind='tool'):
        self.tool_calls += 1
        if kind == 'model':
            self.model_calls += 1
        if kind == 'external':
            self.external_fetches += 1
        if self.tool_calls > self.max_tool_calls or self.model_calls > self.max_model_calls or self.external_fetches > self.max_external_fetches or self.remaining() <= 0:
            raise PlanningBudgetExceeded('Planning reached its execution limit. Review the saved result or start a new job.')

    def remaining(self):
        return self.max_seconds - (monotonic() - self.started)
