"""
Replay timeline event extraction (ONDA 3, R1.1).

This module turns the artefacts already produced by a finished CIVIS
session (transcript + judge verdict + contradiction and honeytoken
reports) into a flat list of :class:`ReplayEvent` records, one per
noteworthy moment in the session.

The list is what the timeline view (:mod:`civis.web.replay_view`)
renders as coloured dots on a horizontal bar. Rendering is a separate
concern — this module has zero Streamlit dependency so it can be
covered by plain unit tests.

Design notes:
    - We DO NOT re-run any detection here. The judge already picked
      out cited turns; the contradiction and honeytoken detectors
      already produced their reports. We just walk those artefacts
      and translate them into a uniform shape.
    - Events keep the ``turn_index`` from the source artefact.
      Positioning on the bar (turn_index / total_turns) is the
      view's job.
    - Severities are intentionally coarse (positive / warning /
      critical / neutral). Fine-grained scoring is what the rubric
      is for; the timeline is a bird's-eye view.
    - Action and queue turns produced by the web layer show up as
      neutral markers so a viewer can tell 'attendant clicked
      something' from persona speech even before hovering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from civis.judge.rubric import JudgeVerdict
from civis.session.storage import SessionTranscript

# Event taxonomy. Kept as string literals so the tests can pin them
# and the view can switch on them without importing an Enum.
EventType = Literal[
    "citation",
    "contradiction",
    "honeytoken_leak",
    "action",
    "queue",
]
Severity = Literal["positive", "warning", "critical", "neutral"]


@dataclass(frozen=True)
class ReplayEvent:
    """
    One dot on the replay timeline.

    Attributes:
        turn_index: Zero-based turn the event lives on. The view uses
            this together with the total number of turns to place the
            dot horizontally.
        event_type: What kind of moment this dot marks. See
            :data:`EventType` for the closed set.
        severity: Colour bucket. Rubric citations with a high score
            map to ``positive``; low scores map to ``critical``; the
            middle band is ``warning``. Contradictions and honeytoken
            leaks are always ``critical``. Actions and queue events
            are ``neutral``.
        label: Short pt-BR text shown on hover.
        criterion: The rubric key (fact_verification, ...) when the
            event came from a citation, else ``None``.
    """

    turn_index: int
    event_type: EventType
    severity: Severity
    label: str
    criterion: str | None = None


# Score thresholds that map a rubric citation score to a severity
# bucket. 5 alone is 'positive'; 0-2 is 'critical'; anything in
# between is 'warning'. Kept as constants so tests can pin them.
_POSITIVE_MIN_SCORE = 5
_CRITICAL_MAX_SCORE = 2


def _severity_for_score(score: int) -> Severity:
    """Bucket a criterion score into a timeline severity."""
    if score >= _POSITIVE_MIN_SCORE:
        return "positive"
    if score <= _CRITICAL_MAX_SCORE:
        return "critical"
    return "warning"


def _criterion_label(criterion_key: str) -> str:
    """
    Short pt-BR label per rubric criterion. Duplicated here (instead
    of importing from :mod:`civis.web.formatting`) to keep this
    module UI-agnostic — the view is free to use a richer label.
    """
    return {
        "fact_verification": "Verificação",
        "data_protection": "Proteção de dados",
        "protocol_adherence": "Protocolo",
        "communication": "Comunicação",
    }.get(criterion_key, criterion_key)


def _summarise_json_payload(content: str, fallback: str) -> str:
    """
    Try to extract a human-readable summary from a JSON turn payload.
    Both ``action`` and ``queue`` turns store a JSON string in
    ``content``; on parse failure we return ``fallback`` so the
    timeline still gets a sensible tooltip.
    """
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    label = parsed.get("label") or parsed.get("id") or fallback
    return str(label)


def _events_from_verdict(verdict: JudgeVerdict | None) -> list[ReplayEvent]:
    """
    Emit one ``citation`` event per cited turn of every criterion.

    Severity comes from the criterion score, not the turn: a score
    of 5 means every cited turn on that criterion is a good moment;
    a score of 1 means every cited turn is a bad moment. Rendering
    all citations of a criterion with the same colour keeps the
    dashboard honest — the judge scores the criterion as a whole.
    """
    if verdict is None:
        return []
    events: list[ReplayEvent] = []
    for criterion in verdict.criteria:
        severity = _severity_for_score(criterion.score)
        label_prefix = _criterion_label(criterion.criterion.value)
        for cite in criterion.cited_turns:
            excerpt = (cite.excerpt or "").strip()
            # Truncate the excerpt so the hover tooltip never turns
            # into a paragraph — 60 chars fits comfortably in a
            # native <title> attribute.
            if len(excerpt) > 60:
                excerpt = excerpt[:57].rstrip() + "..."
            label = (
                f"{label_prefix} ({criterion.score}/5)"
                if not excerpt
                else f"{label_prefix} ({criterion.score}/5) — {excerpt}"
            )
            events.append(
                ReplayEvent(
                    turn_index=cite.turn_index,
                    event_type="citation",
                    severity=severity,
                    label=label,
                    criterion=criterion.criterion.value,
                )
            )
    return events


def _events_from_contradictions(
    contradictions: dict[str, Any] | None,
) -> list[ReplayEvent]:
    """
    Emit one ``contradiction`` event per divergence found by the
    detector. Always ``critical`` — a contradiction is by definition
    the persona giving inconsistent information.
    """
    if not isinstance(contradictions, dict):
        return []
    raw = contradictions.get("contradictions")
    if not isinstance(raw, list):
        return []

    events: list[ReplayEvent] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            turn_index = int(row["turn_index"])
        except (KeyError, TypeError, ValueError):
            continue
        fact_key = str(row.get("fact_key", "?"))
        prior = str(row.get("prior_value", "?"))
        new = str(row.get("new_value", "?"))
        label = f"Contradição em {fact_key}: '{prior}' -> '{new}'"
        events.append(
            ReplayEvent(
                turn_index=turn_index,
                event_type="contradiction",
                severity="critical",
                label=label,
            )
        )
    return events


def _events_from_honeytokens(
    honeytokens: dict[str, Any] | None,
) -> list[ReplayEvent]:
    """
    Emit one ``honeytoken_leak`` event per planted-secret leak.
    Always ``critical`` — a leak is a data-protection failure.
    """
    if not isinstance(honeytokens, dict):
        return []
    raw = honeytokens.get("leaks")
    if not isinstance(raw, list):
        return []

    events: list[ReplayEvent] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            turn_index = int(row["turn_index"])
        except (KeyError, TypeError, ValueError):
            continue
        fact_key = str(row.get("fact_key", "?"))
        label = f"Honeytoken vazado ({fact_key})"
        events.append(
            ReplayEvent(
                turn_index=turn_index,
                event_type="honeytoken_leak",
                severity="critical",
                label=label,
            )
        )
    return events


def _events_from_transcript(transcript: SessionTranscript) -> list[ReplayEvent]:
    """
    Emit neutral markers for structural non-speech turns:

        - ``action`` turns from clickable-button emissions.
        - ``queue`` turns from the pressure-timer.

    Payload is a JSON string; we do a best-effort parse but never
    let a malformed payload break the timeline. The dot is worth
    more than the tooltip here — a viewer just wants to know
    'the attendant did something at this point'.
    """
    events: list[ReplayEvent] = []
    for turn in transcript.turns:
        if turn.speaker == "action":
            label = _summarise_json_payload(turn.content, fallback="Ação do atendente")
            events.append(
                ReplayEvent(
                    turn_index=turn.turn_index,
                    event_type="action",
                    severity="neutral",
                    label=label,
                )
            )
        elif turn.speaker == "queue":
            label = _summarise_json_payload(turn.content, fallback="Pressão de fila")
            events.append(
                ReplayEvent(
                    turn_index=turn.turn_index,
                    event_type="queue",
                    severity="neutral",
                    label=label,
                )
            )
    return events


def build_replay_timeline(
    transcript: SessionTranscript,
    verdict: JudgeVerdict | None,
    contradictions: dict[str, Any] | None,
    honeytokens: dict[str, Any] | None,
) -> list[ReplayEvent]:
    """
    Build the full timeline for a session.

    Events are returned sorted primarily by ``turn_index`` and, within
    the same turn, by a deterministic type order so a viewer sees
    citations before the neutral markers on that turn. Duplicate
    (turn_index, event_type, criterion) triples are kept — the judge
    might cite the same turn twice for two different criteria and
    both dots should render.

    The function is tolerant: any of the sidecars may be ``None`` or
    malformed, in which case that source contributes zero events.
    Callers therefore never need to guard the inputs — an unrated
    session with no reports still yields a valid (possibly empty)
    timeline.
    """
    events: list[ReplayEvent] = []
    events.extend(_events_from_verdict(verdict))
    events.extend(_events_from_contradictions(contradictions))
    events.extend(_events_from_honeytokens(honeytokens))
    events.extend(_events_from_transcript(transcript))

    # Deterministic ordering: turn_index asc, then a fixed type order
    # so tests can pin the sequence.
    type_order = {
        "citation": 0,
        "contradiction": 1,
        "honeytoken_leak": 2,
        "action": 3,
        "queue": 4,
    }
    events.sort(key=lambda e: (e.turn_index, type_order.get(e.event_type, 99)))
    return events


__all__ = [
    "EventType",
    "ReplayEvent",
    "Severity",
    "build_replay_timeline",
]
