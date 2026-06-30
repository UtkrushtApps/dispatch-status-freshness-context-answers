"""Real provider client via litellm. Used only on the end-to-end path."""
from __future__ import annotations

import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()


def _model() -> str:
    return os.environ.get("DISPATCH_MODEL", "gpt-4o-mini")


def complete(messages: List[Dict[str, str]]) -> str:
    """Call a real model through litellm. Requires a provider key in env."""
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        raise RuntimeError(
            "No provider key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env "
            "to run the end-to-end agent. (Invariant tests do not need a key.)"
        )
    import litellm

    resp = litellm.completion(
        model=_model(),
        messages=messages,
        temperature=0,
        max_tokens=300,
    )
    return resp["choices"][0]["message"]["content"]
