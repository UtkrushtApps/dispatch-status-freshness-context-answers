"""CLI entrypoint.

Usage:
  python -m agent --selfcheck            # readiness probe, no model call
  python -m agent --ask SHP-2041 "is it on time?"   # end-to-end (needs key)
"""
import argparse
import sys

from agent import fixtures, prompts, schema


def _selfcheck() -> int:
    # Validate fixtures load and conform to expected shapes.
    events = fixtures.load_events()
    assert isinstance(events, list) and events, "event fixtures empty"
    for e in events:
        schema.ShipmentEvent(**e)  # raises on bad shape
    shipments = {e["shipment_id"] for e in events}
    assert len(shipments) >= 2, "need multiple shipments in fixtures"
    # Validate prompt template renders with placeholders.
    rendered = prompts.SYSTEM_INSTRUCTIONS
    assert "current" in rendered.lower(), "system instructions missing"
    # Validate tokenizer is available.
    import tiktoken
    tiktoken.get_encoding("cl100k_base")
    print("selfcheck: OK ({} events, {} shipments)".format(len(events), len(shipments)))
    return 0


def _ask(shipment_id: str, question: str) -> int:
    from agent import context_builder, llm_client
    events = fixtures.load_events()
    payload = context_builder.build_context(shipment_id, question, events)
    msgs = prompts.assemble_messages(payload)
    answer = llm_client.complete(msgs)
    print("\n--- ASSEMBLED EVIDENCE ---")
    print(payload.evidence_block)
    print("\n--- MODEL ANSWER ---")
    print(answer)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="agent")
    p.add_argument("--selfcheck", action="store_true")
    p.add_argument("--ask", metavar="SHIPMENT_ID")
    p.add_argument("question", nargs="?", default="What is the current status and is it on time?")
    args = p.parse_args(argv)
    if args.selfcheck:
        return _selfcheck()
    if args.ask:
        return _ask(args.ask, args.question)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
