"""Opt-in, local-only recording of LLM calls as fine-tuning data (sub-project 7).

Each LLM call becomes one JSONL record: the exact messages, the model's raw output, and a
`target` — the corrected answer the pipeline actually used (the normalized brief, or the patch the
compiler accepted). Training on `messages -> target` teaches a model to stop making the mistakes the
normalizer and the compiler had to catch. Nothing leaves the machine.

Enable with `--record` or SPAWNPOINT_RECORD=1; location: SPAWNPOINT_DATASET_DIR
(default ~/.local/share/spawnpoint/dataset).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import ChatModel, Usage

TASKS = {"Translation": "translate", "GameBrief": "brief", "BriefUpdate": "tweak", "GraphPatch": "creative"}


def enabled_by_env() -> bool:
    return os.environ.get("SPAWNPOINT_RECORD", "").lower() in ("1", "true", "yes", "on")


def default_dir() -> Path:
    env = os.environ.get("SPAWNPOINT_DATASET_DIR")
    return Path(env) if env else Path.home() / ".local" / "share" / "spawnpoint" / "dataset"


@dataclass
class Record:
    task: str
    messages: list[dict]
    schema_name: str
    raw: Any
    model: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    time: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    target: Any = None
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    accepted: bool | None = None
    corrected: bool | None = None  # the pipeline had to fix the model's answer
    meta: dict = field(default_factory=dict)


class Recorder:
    """Collects records for one studio operation, then appends them to the day's JSONL file."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or default_dir()
        self.pending: list[Record] = []

    def wrap(self, llm: ChatModel) -> "RecordingModel":
        return RecordingModel(llm, self)

    def last(self, task: str) -> Record | None:
        for r in reversed(self.pending):
            if r.task == task:
                return r
        return None

    def all(self, task: str) -> list[Record]:
        return [r for r in self.pending if r.task == task]

    def flush(self, accepted: bool, meta: dict | None = None) -> Path | None:
        if not self.pending:
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{time.strftime('%Y-%m-%d')}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for r in self.pending:
                if r.accepted is None:
                    r.accepted = accepted
                r.meta = {**(meta or {}), **r.meta}
                f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")
        self.pending = []
        return path


@dataclass
class RecordingModel:
    """ChatModel proxy that records every call into a Recorder."""

    inner: ChatModel
    recorder: Recorder

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def usage(self) -> Usage:
        return self.inner.usage

    def chat_json(self, messages: list[dict], schema: dict, schema_name: str, **kw) -> dict:
        raw = self.inner.chat_json(messages, schema, schema_name, **kw)
        self.recorder.pending.append(Record(
            task=TASKS.get(schema_name, schema_name), messages=messages, schema_name=schema_name,
            raw=raw, model=self.inner.name))
        return raw


def iter_records(directory: Path | None = None):
    d = directory or default_dir()
    for path in sorted(d.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def stats(directory: Path | None = None) -> dict:
    by_task: Counter = Counter()
    accepted: Counter = Counter()
    corrected: Counter = Counter()
    models: Counter = Counter()
    for r in iter_records(directory):
        t = r["task"]
        by_task[t] += 1
        models[r.get("model", "?")] += 1
        if r.get("accepted"):
            accepted[t] += 1
        if r.get("corrected"):
            corrected[t] += 1
    return {
        "records": sum(by_task.values()),
        "models": dict(models),
        "tasks": {t: {"count": n, "accepted": accepted[t], "corrected": corrected[t]} for t, n in sorted(by_task.items())},
    }
