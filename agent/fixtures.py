"""Fixture loaders for local event data and traces."""
from __future__ import annotations

import json
import os
from typing import List, Dict

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_BASE, "fixtures")


def load_events() -> List[Dict]:
    with open(os.path.join(_FIX, "shipment_events.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def events_for(shipment_id: str) -> List[Dict]:
    return [e for e in load_events() if e["shipment_id"] == shipment_id]


def load_trace(name: str) -> Dict:
    with open(os.path.join(_FIX, "traces", name), "r", encoding="utf-8") as f:
        return json.load(f)
