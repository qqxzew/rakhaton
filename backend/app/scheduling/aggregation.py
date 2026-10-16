"""Readiness aggregation: case -> meeting -> day -> dashboard. Severity order: not_ready > attention > ready."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.pipeline.readiness import SEVERITY

EMPTY_MEETING_REASON = "Žádní pacienti"
EMPTY_MEETING_STATE = "attention"


@dataclass
class Counts:
    ready: int = 0
    attention: int = 0
    not_ready: int = 0

    def add(self, state: str) -> None:
        setattr(self, state, getattr(self, state) + 1)

    @property
    def total(self) -> int:
        return self.ready + self.attention + self.not_ready

    def merge(self, other: Counts) -> None:
        self.ready += other.ready
        self.attention += other.attention
        self.not_ready += other.not_ready


@dataclass
class Aggregate:
    state: str
    reason: str
    counts: Counts = field(default_factory=Counts)


def aggregate_items(items: list[tuple[str, str]]) -> Aggregate:
    """Most severe (state, reason) wins; the first of equal severity keeps its reason."""
    counts = Counts()
    worst: tuple[str, str] | None = None
    for state, reason in items:
        counts.add(state)
        if worst is None or SEVERITY[state] > SEVERITY[worst[0]]:
            worst = (state, reason)
    assert worst is not None
    return Aggregate(worst[0], worst[1], counts)


def meeting_aggregate(case_states: list[tuple[str, str]]) -> Aggregate:
    """Readiness of a meeting from its cases; an empty meeting needs attention."""
    if not case_states:
        return Aggregate(EMPTY_MEETING_STATE, EMPTY_MEETING_REASON, Counts())
    return aggregate_items(case_states)


def day_aggregate(meetings: list[tuple[str, str]]) -> Aggregate | None:
    """Readiness of a day from its meetings' (state, reason); `None` for a day without meetings."""
    return aggregate_items(meetings) if meetings else None


def dashboard_aggregate(days: list[Aggregate | None]) -> Aggregate | None:
    """Window totals: counts are per meeting (summed over the days), state and reason come from the worst day."""
    scheduled = [d for d in days if d is not None]
    if not scheduled:
        return None
    total = aggregate_items([(d.state, d.reason) for d in scheduled])
    total.counts = Counts()
    for d in scheduled:
        total.counts.merge(d.counts)
    return total
