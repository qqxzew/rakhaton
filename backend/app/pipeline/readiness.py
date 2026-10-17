"""Readiness of a case (CLAUDE.md 9.9). Always returns a state with a short Czech reason."""

from __future__ import annotations

from app.pipeline.rules import fmt_date
from app.pipeline.schemas import OpenIssue, Readiness, RequiredItem

SEVERITY: dict[str, int] = {"ready": 0, "attention": 1, "not_ready": 2}


def _missing_label(item: RequiredItem) -> str:
    base = f"{item.modality} {fmt_date(item.target_date)}"
    if item.availability == "not_in_pacs":
        return f"Chybí: {base} (snímky nejsou v PACS)"
    site = f" ({item.holding_site_name})" if item.holding_site_name else ""
    return f"Chybí: {base}{site}"


def compute_readiness(
    check_status: str,
    items: list[RequiredItem],
    issues: list[OpenIssue],
    *,
    pending_approval: bool = False,
    conflict: bool = False,
) -> tuple[Readiness, str]:
    if check_status in ("pending", "running"):
        return "not_ready", "Probíhá úvodní kontrola"
    if check_status == "failed":
        return "not_ready", "Nepodařilo se načíst záznamy pacienta"
    missing = [i for i in items if i.state == "missing" and not i.waived]
    if missing:
        return "not_ready", _missing_label(missing[0])
    attention = [i for i in items if i.state == "attention" and not i.waived]
    if attention:
        first = attention[0]
        return "attention", first.note or f"Vyžaduje ověření: {first.modality} {fmt_date(first.target_date)}"
    if pending_approval:
        return "attention", "Čeká se na schválení žádosti"
    if conflict:
        return "attention", "Konflikt v datech"
    if issues:
        return "attention", issues[0].text
    if not items:
        return "attention", "Nenalezena žádná předchozí vyšetření"
    return "ready", "Všechna požadovaná vyšetření ověřena"


def worst(states: list[str]) -> str:
    return max(states, key=lambda s: SEVERITY[s]) if states else "attention"
