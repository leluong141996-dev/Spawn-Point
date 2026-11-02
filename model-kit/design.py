#!/usr/bin/env python3
"""SpawnPoint-Coder-7B without Spawn Point: a game idea in, the game's design out, as JSON. Standard library only.

    python design.py "a ninja platformer where you collect stars"                 # a new design
    python design.py "make it night and add bats" --change design.json           # change a design

The model answers any OpenAI-compatible server with JSON-schema output:
    Ollama:  ollama pull hf.co/smoky1496/SpawnPoint-Coder-7B-GGUF:Q4_K_M   (the default below)
    vLLM:    BASE_URL=http://localhost:8000/v1 MODEL=SpawnPoint-Coder-7B python design.py "..."

Build a playable Godot 4 game from the answer with Spawn Point:
    pip install spawnpoint-studio && spawnpoint create "my game" --brief design.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_URL = os.environ.get("BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("MODEL", "hf.co/smoky1496/SpawnPoint-Coder-7B-GGUF:Q4_K_M")


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def ask(messages: list[dict], schema: dict, name: str, temperature: float) -> dict:
    payload = {"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": 1500,
               "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}}
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(json.loads(resp.read())["choices"][0]["message"]["content"])


def design(idea: str) -> dict:
    """The prompt Spawn Point sends: the base rules, plus the farm or card-game words when the idea asks for one."""
    p = load("prompts.json")
    system = p["design_system"]
    if re.search(p["farm_words"], idea, re.I):
        system += "\n" + p["farm_line"]
    if re.search(p["card_words"], idea, re.I):
        system += "\n" + p["card_line"]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": idea}]
    return ask(messages, load("design.schema.json"), "GameBrief", 0.4)


def change(current: dict, request: str) -> dict:
    p = load("prompts.json")
    messages = [{"role": "system", "content": p["tweak_system"]},
                {"role": "user", "content": f"Game: {json.dumps(current)}\nRequest: {request}"}]
    return ask(messages, load("tweak.schema.json"), "BriefUpdate", 0.1)["brief"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("text", help="the game idea, or the change you want")
    ap.add_argument("--change", type=Path, metavar="DESIGN.json", help="change this design instead of making a new one")
    args = ap.parse_args()
    if args.change:
        result = change(json.loads(args.change.read_text(encoding="utf-8")), args.text)
    else:
        result = design(args.text)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
