"""Structured diagnostics — the feedback channel for humans and for the LLM orchestrator."""

from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Diagnostic:
    severity: Severity
    code: str
    path: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["hint"] is None:
            del d["hint"]
        return d

    def __str__(self) -> str:
        s = f"{self.severity}[{self.code}] {self.path}: {self.message}"
        if self.hint:
            s += f" (hint: {self.hint})"
        return s


@dataclass
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)

    def error(self, code: str, path: str, message: str, hint: str | None = None) -> None:
        self.items.append(Diagnostic("error", code, path, message, hint))

    def warning(self, code: str, path: str, message: str, hint: str | None = None) -> None:
        self.items.append(Diagnostic("warning", code, path, message, hint))

    def extend(self, other: Iterable[Diagnostic]) -> None:
        self.items.extend(other)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


def did_you_mean(word: str, options: Iterable[str]) -> str | None:
    """Return a 'Did you mean ...?' hint, or a list of valid options when nothing is close."""
    opts = sorted(set(options))
    if not opts:
        return None
    close = difflib.get_close_matches(word, opts, n=1, cutoff=0.6)
    if not close:
        lowered = {o.lower(): o for o in opts}
        if word.lower() in lowered:
            close = [lowered[word.lower()]]
    if close:
        return f"Did you mean '{close[0]}'?"
    if len(opts) <= 24:
        return "Valid options: " + ", ".join(opts)
    return None


def join_path(*parts: object) -> str:
    out = ""
    for p in parts:
        if isinstance(p, int):
            out += f"[{p}]"
        elif out:
            out += f".{p}"
        else:
            out = str(p)
    return out
