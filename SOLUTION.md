# Solution Steps

1. Implement `retrieval.resolve_current_event` so it never relies on incoming list order. First handle empty or structurally ambiguous evidence, then mark any event referenced by another event's `supersedes` field as replaced, and finally choose the latest non-superseded event by `recorded_at` with `seq` as the tie-breaker.

2. Return `None` from current-status resolution when the evidence cannot establish one authoritative event, such as duplicate event ids, self-supersession, invalid recency keys, no active events, or an unbreakable latest tie. This allows the prompt to produce an uncertain answer instead of inventing a status.

3. Implement `retrieval.order_evidence` to return shallow copies of shipment events with renderer metadata: `_is_current`, `_is_superseded`, and `_superseded_by`. Sort the known current event first, then active history newest-to-oldest, then superseded/corrected history newest-to-oldest.

4. In `context_builder.build_context`, filter `all_events` strictly to the requested `shipment_id` before doing any selection so foreign shipment evidence cannot leak into the prompt.

5. Render a compact evidence header that explicitly says either `CURRENT STATUS: ... event_id=...` or `CURRENT STATUS: UNKNOWN / NOT ESTABLISHED`. This makes the resolved status visible in the actual prompt text, not just in the returned dataclass fields.

6. Render every included event as a single evidence item containing its stable `event_id`, status, timestamp, sequence number, supersession metadata, and detail. Mark items as `[CURRENT]`, `[HISTORY]`, or `[SUPERSEDED]` so corrections and old statuses are not presented with equal authority.

7. Use `tiktoken` with the `cl100k_base` encoding to compute the token count for the evidence block. Add event lines only while the rendered block remains at or below `MAX_EVIDENCE_TOKENS`. Prefer current/recent evidence and omit older lines when necessary.

8. Add adaptive truncation for status/detail text so long histories or unusually verbose event details still fit inside the configured evidence-token budget while preserving event ids and current-status attribution.

9. Return a `ContextPayload` populated with the requested shipment id, original question, selected event ids in render order, resolved `current_event_id` or `None`, the rendered evidence block, and the exact token count.

10. Run `python -m agent --selfcheck` and `python -m pytest -q invariants` to verify fixture loading, current-status resolution, attribution, shipment filtering, current marker rendering, unknown shipment handling, and token-budget compliance.

