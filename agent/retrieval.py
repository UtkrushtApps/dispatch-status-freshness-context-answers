"""Evidence selection helpers for the dispatch status assistant.

The candidate implements the selection/ordering logic here. These functions feed
the context builder. They must NOT call the model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


def _parse_recorded_at(value: object) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp as UTC, returning None for bad values."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _seq(value: object) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _recency_key(event: Dict) -> Optional[Tuple[datetime, int]]:
    """Return the authoritative ordering key: recorded_at, then seq."""
    dt = _parse_recorded_at(event.get("recorded_at"))
    seq = _seq(event.get("seq"))
    if dt is None or seq is None:
        return None
    return (dt, seq)


def _event_ids(events: List[Dict]) -> List[str]:
    return [str(e.get("event_id", "")) for e in events]


def _superseded_by_map(events: List[Dict]) -> Dict[str, List[str]]:
    """Map superseded event_id -> correcting event_id(s), limited to this shipment.

    Unknown references are ignored for the purpose of marking old local evidence:
    a correction can still be an active event even if the replaced event was not
    present in the input slice.
    """
    ids = set(_event_ids(events))
    mapping: Dict[str, List[str]] = {}
    for event in events:
        event_id = str(event.get("event_id", ""))
        supersedes = event.get("supersedes")
        if supersedes is None:
            continue
        supersedes_id = str(supersedes)
        if supersedes_id and supersedes_id in ids and supersedes_id != event_id:
            mapping.setdefault(supersedes_id, []).append(event_id)
    return mapping


def resolve_current_event(events: List[Dict]) -> Optional[Dict]:
    """Return the single authoritative current event for one shipment, or None.

    Rules implemented here:
      1. An event referenced by another event's ``supersedes`` field is a
         corrected/replaced historical event and cannot be current.
      2. Among non-superseded events, the most recent ``recorded_at`` timestamp is
         current; ``seq`` breaks timestamp ties.
      3. If the evidence is structurally ambiguous (duplicate ids, self-
         supersession, invalid recency keys, or an unbreakable latest tie), return
         None so the prompt can tell the agent to be uncertain rather than invent
         a current status.
    """
    if not events:
        return None

    ids = _event_ids(events)
    if len(ids) != len(set(ids)):
        return None

    for event in events:
        if event.get("supersedes") is not None and str(event.get("supersedes")) == str(event.get("event_id")):
            return None

    superseded_ids = set(_superseded_by_map(events).keys())
    active_events = [e for e in events if str(e.get("event_id", "")) not in superseded_ids]
    if not active_events:
        return None

    keyed: List[Tuple[Tuple[datetime, int], Dict]] = []
    for event in active_events:
        key = _recency_key(event)
        if key is None:
            return None
        keyed.append((key, event))

    max_key = max(key for key, _ in keyed)
    latest = [event for key, event in keyed if key == max_key]
    if len(latest) != 1:
        return None
    return latest[0]


def order_evidence(events: List[Dict]) -> List[Dict]:
    """Return events for ONE shipment ordered so the current status is unambiguous.

    The returned dictionaries are shallow copies with helper flags used by the
    renderer:
      - ``_is_current``: the resolved authoritative current event
      - ``_is_superseded``: this event has been corrected/replaced
      - ``_superseded_by``: event ids that supersede this event

    Current evidence is placed first when known, followed by active historical
    events newest-to-oldest, then superseded events newest-to-oldest. If no
    current event can be established, everything is shown newest-to-oldest with
    no current marker.
    """
    if not events:
        return []

    current = resolve_current_event(events)
    current_id = str(current.get("event_id")) if current is not None else None
    superseded_by = _superseded_by_map(events)

    copied: List[Dict] = []
    for event in events:
        item = dict(event)
        event_id = str(item.get("event_id", ""))
        correcting_ids = sorted(superseded_by.get(event_id, []))
        item["_is_current"] = current_id is not None and event_id == current_id
        item["_is_superseded"] = bool(correcting_ids)
        item["_superseded_by"] = correcting_ids
        copied.append(item)

    def sort_key(event: Dict) -> Tuple[int, float, int, str]:
        event_id = str(event.get("event_id", ""))
        if current_id is not None and event_id == current_id:
            rank = 0
        elif event.get("_is_superseded"):
            rank = 2
        else:
            rank = 1

        dt = _parse_recorded_at(event.get("recorded_at"))
        ts = dt.timestamp() if dt is not None else float("-inf")
        seq = _seq(event.get("seq"))
        seq_value = seq if seq is not None else -1
        # rank ascending; recency and seq descending; event id ascending stable tie.
        return (rank, -ts, -seq_value, event_id)

    return sorted(copied, key=sort_key)
