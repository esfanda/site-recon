#!/usr/bin/env python3
"""The model sometimes answers with the schema wrapped around the payload.

Seen live on 2026-08-21: a Persian scan finished after five minutes and
rendered a completely blank report, because every section sat one level down
inside `properties` and the runner read them all as missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_recon.llm import _unwrap_schema_envelope


def main() -> int:
    wrapped = {
        "type": "object",
        "properties": {
            "claim_audit": {"value_proposition": "x"},
            "hygiene": {"items": []},
        },
    }
    got = _unwrap_schema_envelope(wrapped)
    assert got == wrapped["properties"], got
    assert got["claim_audit"]["value_proposition"] == "x"

    plain = {"claim_audit": {"value_proposition": "y"}, "hygiene": {"items": []}}
    assert _unwrap_schema_envelope(plain) == plain

    # A real payload that happens to carry a "type" key must survive untouched.
    tricky = {"type": "object", "claim_audit": {"value_proposition": "z"}}
    assert _unwrap_schema_envelope(tricky) == tricky

    assert _unwrap_schema_envelope(None) is None
    assert _unwrap_schema_envelope([1, 2]) == [1, 2]

    print("PASS: schema envelope unwrapped, plain payloads untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
