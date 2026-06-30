"""Assemble the grounded context payload for the dispatch status assistant.

This is the primary file the candidate completes. It selects evidence for the
requested shipment, renders an attributable evidence block, marks the current
status unambiguously, and respects a token ceiling. It must NOT call the model.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import tiktoken

from agent import retrieval
from agent.schema import ContextPayload

# Maximum tokens allowed for the rendered evidence block (cl100k_base).
MAX_EVIDENCE_TOKENS = 600

_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _clean(value: object) -> str:
    """Render a value as single-line prompt-safe evidence text."""
    if value is None:
        return "none"
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def _truncate(text: object, max_chars: int) -> str:
    value = _clean(text)
    if max_chars < 1:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars == 1:
        return "…"
    return value[: max_chars - 1].rstrip() + "…"


def _current_header(shipment_id: str, current: Optional[Dict]) -> List[str]:
    if current is None:
        return [
            f"SHIPMENT_ID: {_truncate(shipment_id, 120)}",
            "CURRENT STATUS: UNKNOWN / NOT ESTABLISHED from the available events.",
            "Evidence items (newest first; no item is marked CURRENT):",
        ]
    return [
        f"SHIPMENT_ID: {_truncate(shipment_id, 120)}",
        (
            "CURRENT STATUS: "
            f"{_truncate(current.get('status'), 120)} "
            f"(event_id={_clean(current.get('event_id'))}, "
            f"recorded_at={_clean(current.get('recorded_at'))}, "
            f"seq={_clean(current.get('seq'))})"
        ),
        "Evidence items (CURRENT first; superseded entries, if included, are not current):",
    ]


def _marker(event: Dict, current_id: Optional[str]) -> str:
    event_id = _clean(event.get("event_id"))
    if current_id is not None and event_id == current_id:
        return "CURRENT"
    if event.get("_is_superseded"):
        return "SUPERSEDED"
    return "HISTORY"


def _render_event_line(event: Dict, marker: str, status_chars: int, detail_chars: int) -> str:
    event_id = _clean(event.get("event_id"))
    status = _truncate(event.get("status"), status_chars)
    recorded_at = _clean(event.get("recorded_at"))
    seq = _clean(event.get("seq"))
    supersedes = _clean(event.get("supersedes"))

    superseded_by_part = ""
    superseded_by = event.get("_superseded_by") or []
    if superseded_by:
        superseded_by_part = " superseded_by=" + ",".join(_clean(x) for x in superseded_by)

    detail_part = ""
    detail = _truncate(event.get("detail"), detail_chars)
    if detail:
        detail_part = f' detail="{detail}"'

    return (
        f'- [{marker}] event_id={event_id} status="{status}" '
        f"recorded_at={recorded_at} seq={seq} supersedes={supersedes}"
        f"{superseded_by_part}{detail_part}"
    )


def _block(lines: Iterable[str]) -> str:
    return "\n".join(lines).strip()


def _append_if_fits(lines: List[str], line: str) -> bool:
    candidate = _block([*lines, line])
    if count_tokens(candidate) <= MAX_EVIDENCE_TOKENS:
        lines.append(line)
        return True
    return False


def _fit_event_line(lines: List[str], event: Dict, marker: str) -> Optional[str]:
    """Return the richest event line that fits the remaining budget."""
    for status_chars in (160, 120, 80, 40, 20):
        for detail_chars in (240, 180, 120, 80, 40, 20, 0):
            line = _render_event_line(event, marker, status_chars, detail_chars)
            if count_tokens(_block([*lines, line])) <= MAX_EVIDENCE_TOKENS:
                return line

    # Last-resort minimal attributable line. This should fit for normal ids even
    # when details/statuses are extremely large.
    minimal = (
        f"- [{marker}] event_id={_clean(event.get('event_id'))} "
        f"status=\"{_truncate(event.get('status'), 12)}\" "
        f"recorded_at={_clean(event.get('recorded_at'))} seq={_clean(event.get('seq'))}"
    )
    if count_tokens(_block([*lines, minimal])) <= MAX_EVIDENCE_TOKENS:
        return minimal
    return None


def _fit_initial_lines(shipment_id: str, current: Optional[Dict]) -> List[str]:
    """Build a header and shrink it if unusual input would exceed the budget."""
    lines = _current_header(shipment_id, current)
    if count_tokens(_block(lines)) <= MAX_EVIDENCE_TOKENS:
        return lines

    if current is None:
        lines = [
            f"SHIPMENT_ID: {_truncate(shipment_id, 40)}",
            "CURRENT STATUS: UNKNOWN",
            "Evidence items:",
        ]
    else:
        lines = [
            f"SHIPMENT_ID: {_truncate(shipment_id, 40)}",
            f"CURRENT STATUS: event_id={_clean(current.get('event_id'))} status={_truncate(current.get('status'), 40)}",
            "Evidence items:",
        ]
    if count_tokens(_block(lines)) <= MAX_EVIDENCE_TOKENS:
        return lines

    # Pathological final fallback.
    if current is None:
        return ["CURRENT STATUS: UNKNOWN"]
    return [f"CURRENT STATUS: event_id={_clean(current.get('event_id'))}"]


def build_context(shipment_id: str, question: str, all_events: List[Dict]) -> ContextPayload:
    """Build the grounded ContextPayload for one shipment.

    Requirements (see invariants/ for exact checks):
      - Use only events for `shipment_id`.
      - Each rendered evidence item must carry its event_id for attribution.
      - The payload must mark which event is current (current_event_id) when it
        can be established, else None.
      - evidence_block token_count must stay within MAX_EVIDENCE_TOKENS.
    """
    shipment_events = [dict(e) for e in all_events if e.get("shipment_id") == shipment_id]
    current = retrieval.resolve_current_event(shipment_events)
    current_id = _clean(current.get("event_id")) if current is not None else None
    ordered_events = retrieval.order_evidence(shipment_events)

    lines = _fit_initial_lines(shipment_id, current)
    selected_event_ids: List[str] = []

    if not ordered_events:
        no_events_line = "No status events were found for this shipment in the provided evidence."
        _append_if_fits(lines, no_events_line)
    else:
        omitted = 0
        for event in ordered_events:
            marker = _marker(event, current_id)
            line = _fit_event_line(lines, event, marker)
            if line is None:
                omitted += 1
                continue
            lines.append(line)
            selected_event_ids.append(_clean(event.get("event_id")))

        if omitted:
            note = f"... {omitted} additional event(s) omitted to stay within the evidence token budget."
            _append_if_fits(lines, note)

    # Defensive guarantee: if a current event exists, keep at least an attributable
    # current line, even if all other history had to be dropped.
    if current is not None and current_id not in selected_event_ids:
        fallback_lines = _fit_initial_lines(shipment_id, current)
        line = _fit_event_line(fallback_lines, current, "CURRENT")
        if line is not None:
            fallback_lines.append(line)
            lines = fallback_lines
            selected_event_ids = [current_id]

    evidence_block = _block(lines)
    token_count = count_tokens(evidence_block)

    # The fitting routines should keep this true. If future changes break that,
    # degrade safely rather than returning an over-budget prompt.
    if token_count > MAX_EVIDENCE_TOKENS:
        if current is None:
            evidence_block = "CURRENT STATUS: UNKNOWN"
            selected_event_ids = []
        else:
            evidence_block = f"CURRENT STATUS: event_id={current_id} status={_truncate(current.get('status'), 40)}"
            selected_event_ids = []
        token_count = count_tokens(evidence_block)

    return ContextPayload(
        shipment_id=shipment_id,
        question=question,
        selected_event_ids=selected_event_ids,
        current_event_id=current_id,
        evidence_block=evidence_block,
        token_count=token_count,
    )
