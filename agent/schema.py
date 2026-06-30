"""Typed context schema for the dispatch status assistant."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ShipmentEvent:
    """A single status event from the event store.

    recorded_at is an ISO-8601 UTC timestamp string. seq is a monotonically
    increasing store sequence id (tie-breaker when timestamps collide).
    supersedes is the event_id this entry corrects/replaces, or None.
    """

    event_id: str
    shipment_id: str
    status: str
    detail: str
    recorded_at: str
    seq: int
    supersedes: Optional[str] = None


@dataclass
class ContextPayload:
    """The assembled context returned by the candidate's context builder.

    - shipment_id: the requested shipment
    - question: the user's question (untrusted input)
    - selected_event_ids: event_ids included as evidence, in render order
    - current_event_id: the event_id the builder considers authoritative/current,
      or None if the builder cannot establish a current status
    - evidence_block: the rendered evidence string injected into the prompt
    - token_count: token count of evidence_block under cl100k_base
    """

    shipment_id: str
    question: str
    selected_event_ids: List[str] = field(default_factory=list)
    current_event_id: Optional[str] = None
    evidence_block: str = ""
    token_count: int = 0
