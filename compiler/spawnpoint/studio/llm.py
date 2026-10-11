"""Minimal OpenAI-compatible chat client with structured (JSON-schema) output.

Works with vLLM, Ollama, OpenAI, and any server implementing /v1/chat/completions with
`response_format: {"type": "json_schema"}`. No third-party dependencies.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_BASE_URL = "http://localhost:8000/v1"  # vLLM (spawnpoint llm up on an NVIDIA GPU)
OLLAMA_BASE_URL = "http://localhost:11434/v1"  # Ollama (spawnpoint llm up elsewhere)


def _answers(base_url: str) -> bool:
    try:
        urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=0.5)
        return True
    except Exception:
        return False


def default_base_url() -> str:
    """$SPAWNPOINT_LLM_BASE_URL, else the local vLLM server, else a local Ollama, else the vLLM address."""
    env = os.environ.get("SPAWNPOINT_LLM_BASE_URL")
    if env:
        return env
    if not _answers(DEFAULT_BASE_URL) and _answers(OLLAMA_BASE_URL):
        return OLLAMA_BASE_URL
    return DEFAULT_BASE_URL


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.seconds += other.seconds

    def __str__(self) -> str:
        return (f"{self.calls} call(s), {self.prompt_tokens} prompt + {self.completion_tokens} completion tokens, "
                f"{self.seconds:.1f}s")


class ChatModel(Protocol):
    name: str
    usage: Usage

    def chat_json(self, messages: list[dict], schema: dict, schema_name: str, *,
                  temperature: float = 0.3, max_tokens: int = 1500) -> dict: ...


@dataclass
class OpenAICompatible:
    base_url: str = field(default_factory=default_base_url)
    model: str | None = field(default_factory=lambda: os.environ.get("SPAWNPOINT_LLM_MODEL"))
    api_key: str | None = field(default_factory=lambda: os.environ.get("SPAWNPOINT_LLM_API_KEY"))
    timeout: float = 180.0
    usage: Usage = field(default_factory=Usage)

    @property
    def name(self) -> str:
        return self.model or "?"

    def _request(self, path: str, payload: dict | None = None) -> dict:
        url = self.base_url.rstrip("/") + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:500]
            raise LLMError(f"LLM server returned {e.code} for {path}: {body}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise LLMError(
                f"cannot reach the LLM at {self.base_url} ({e}). Start it with `spawnpoint llm up` "
                "or set SPAWNPOINT_LLM_BASE_URL.") from e

    def resolve_model(self) -> str:
        if not self.model:
            models = self._request("/models").get("data", [])
            if not models:
                raise LLMError(f"the LLM server at {self.base_url} lists no models")
            self.model = pick_model(models)
        return self.model

    def chat_json(self, messages: list[dict], schema: dict, schema_name: str, *,
                  temperature: float = 0.3, max_tokens: int = 1500) -> dict:
        payload: dict[str, Any] = {
            "model": self.resolve_model(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
        }
        t0 = time.perf_counter()
        resp = self._request("/chat/completions", payload)
        elapsed = time.perf_counter() - t0
        u = resp.get("usage") or {}
        self.usage.add(Usage(1, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), elapsed))
        try:
            content = resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected LLM response: {str(resp)[:300]}") from e
        return parse_json(content)


def pick_model(models: list[dict]) -> str:
    """SpawnPoint-Coder if the server has it (Ollama lists every local model), else a fine-tuned adapter
    (vLLM lists it with a `parent`) over the base model it sits on, else the first model."""
    ours = [m for m in models if "spawnpoint" in m["id"].lower()]
    adapters = [m for m in models if m.get("parent")]
    return (ours or adapters or models)[0]["id"]


def parse_json(content: str) -> dict:
    """Parse model output; tolerate code fences or text around a JSON object."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError(f"LLM did not return valid JSON: {text[:300]}")


@dataclass
class ScriptedModel:
    """Test double: returns canned responses in order and records the prompts it saw."""

    responses: list[dict]
    name: str = "scripted"
    usage: Usage = field(default_factory=Usage)
    seen: list[list[dict]] = field(default_factory=list)

    def chat_json(self, messages: list[dict], schema: dict, schema_name: str, *,
                  temperature: float = 0.3, max_tokens: int = 1500) -> dict:
        self.seen.append(messages)
        self.usage.add(Usage(1, 0, 0, 0.0))
        if not self.responses:
            raise LLMError("scripted model ran out of responses")
        return self.responses.pop(0)
