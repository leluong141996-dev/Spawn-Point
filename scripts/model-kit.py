#!/usr/bin/env python3
"""Writes model-kit/: what it takes to call SpawnPoint-Coder-7B without Spawn Point (the prompts and the JSON schemas
the tool sends). The same files are uploaded next to the model on Hugging Face.

    python scripts/model-kit.py            # rewrite model-kit/*.json
    python scripts/model-kit.py --check    # exit 1 if they are out of date (the tests run this)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "compiler"))

from spawnpoint.studio import genres, prompts  # noqa: E402

KIT = ROOT / "model-kit"


def files() -> dict[str, str]:
    kit = {
        "design_system": prompts.BRIEF_SYSTEM_V5,
        "farm_line": prompts.FARM_LINE,
        "farm_words": prompts.FARM_WORDS.pattern,
        "card_line": prompts.CARD_LINE,
        "card_words": prompts.CARD_WORDS.pattern,
        "tweak_system": prompts.TWEAK_SYSTEM_V5,
    }
    dump = lambda d: json.dumps(d, indent=1, ensure_ascii=False) + "\n"  # noqa: E731
    return {"prompts.json": dump(kit), "design.schema.json": dump(genres.wire_schema()),
            "tweak.schema.json": dump(genres.wire_tweak_schema())}


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for name, text in files().items():
        path = KIT / name
        if path.exists() and path.read_text() == text:
            continue
        stale.append(name)
        if not check:
            path.write_text(text)
    if check and stale:
        print(f"model-kit is out of date ({', '.join(stale)}): run python scripts/model-kit.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
