"""Offline invariant tests for the assembled context. No model key required."""
import pytest

from agent import fixtures
from agent.context_builder import build_context, MAX_EVIDENCE_TOKENS, count_tokens


def _events():
    return fixtures.load_events()


def test_only_requested_shipment_evidence():
    payload = build_context("SHP-2041", "is it on time?", _events())
    all_events = {e["event_id"]: e for e in _events()}
    for eid in payload.selected_event_ids:
        assert all_events[eid]["shipment_id"] == "SHP-2041", "foreign shipment event leaked into evidence"


def test_current_event_is_latest_for_linear_history():
    # SHP-2041: latest by time is the Delivery Exception EV-1005.
    payload = build_context("SHP-2041", "is it on time?", _events())
    assert payload.current_event_id == "EV-1005", "current status must be the most recent event"


def test_current_event_respects_corrections():
    # SHP-5510: EV-3003 supersedes the exception EV-3002; current must be EV-3003.
    payload = build_context("SHP-5510", "any damage?", _events())
    assert payload.current_event_id == "EV-3003", "superseded event must not be treated as current"
    # The superseded event must not be presented as the live status if included.
    assert payload.current_event_id != "EV-3002"


def test_evidence_items_are_attributable():
    payload = build_context("SHP-7732", "is it delivered?", _events())
    assert payload.selected_event_ids, "no evidence selected"
    for eid in payload.selected_event_ids:
        assert eid in payload.evidence_block, f"event id {eid} missing from rendered evidence (not attributable)"


def test_evidence_block_within_token_budget():
    payload = build_context("SHP-2041", "status?", _events())
    assert payload.token_count <= MAX_EVIDENCE_TOKENS
    assert payload.token_count == count_tokens(payload.evidence_block)


def test_current_marked_in_rendered_block():
    # The current status must be discoverable from the rendered text, not only the field.
    payload = build_context("SHP-7732", "is it delivered?", _events())
    assert payload.current_event_id is not None
    assert payload.current_event_id in payload.evidence_block


def test_handles_unknown_shipment_gracefully():
    payload = build_context("SHP-DOES-NOT-EXIST", "status?", _events())
    assert payload.selected_event_ids == []
    assert payload.current_event_id is None
