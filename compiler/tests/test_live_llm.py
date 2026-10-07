"""End-to-end with the real LLM server (skipped when it is not running). Slow: ~1 min."""

import json
import urllib.request

import pytest

from spawnpoint.studio.llm import OpenAICompatible
from spawnpoint.studio.orchestrator import create, load_session, tweak


def _llm_up() -> bool:
    try:
        urllib.request.urlopen(OpenAICompatible().base_url.rstrip("/") + "/models", timeout=2)
        return True
    except Exception:
        return False


pytestmark = [pytest.mark.llm, pytest.mark.skipif(not _llm_up(), reason="LLM server not running")]


def test_create_then_tweak_vietnamese(tmp_path, manifest):
    out = tmp_path / "game"
    llm = OpenAICompatible()
    res = create("game nhảy bục, nhân vật là ninja, ăn sao để qua màn", out, llm, web_export=False,
                 manifest=manifest)
    assert res.ok
    assert res.brief.genre == "platformer"
    assert res.brief.collectible.count > 0
    before = load_session(out)["brief"]

    res2 = tweak(out, "nhảy cao hơn 20%", llm, web_export=False, manifest=manifest)
    assert res2.ok
    after = load_session(out)["brief"]
    assert after["player"]["jump_tiles"] > before["player"]["jump_tiles"]
    unchanged = {k for k in before if before[k] == after[k]}
    assert {"genre", "enemies", "goal", "length"} <= unchanged, json.dumps(res2.changes)
