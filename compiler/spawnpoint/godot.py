"""Locating and running the Godot binary headless."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

CANDIDATES = ("godot4", "godot", "Godot", "godot-4")

# Lines Godot prints at exit in headless mode that are not problems of the game.
_NOISE = (
    "RID allocations of type",
    "were leaked at exit",
    "ObjectDB instances leaked at exit",
    "resources still in use at exit",
    "at: cleanup",
    "at: clear",
    "at: finalize",
)


class GodotError(RuntimeError):
    def __init__(self, message: str, output: str = ""):
        super().__init__(message)
        self.output = output


@dataclass
class RunResult:
    returncode: int
    output: str

    @property
    def script_errors(self) -> list[str]:
        return find_errors(self.output)


def find_binary() -> str:
    env = os.environ.get("GODOT_BIN") or os.environ.get("GODOT")
    if env:
        return env
    for c in CANDIDATES:
        path = shutil.which(c)
        if path:
            return path
    from .installer import managed_binary
    if managed_binary().exists():  # installed by `spawnpoint setup`
        return str(managed_binary())
    raise GodotError("Godot 4 not found. Run `spawnpoint setup` to install it, or set GODOT_BIN=/path/to/godot.")


def available() -> bool:
    try:
        find_binary()
        return True
    except GodotError:
        return False


def version() -> str:
    out = subprocess.run([find_binary(), "--version"], capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


def run(project: Path, args: list[str], timeout: float = 180) -> RunResult:
    cmd = [find_binary(), "--headless", "--path", str(project), *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        raise GodotError(f"Godot timed out after {timeout}s: {' '.join(cmd)}", out) from e
    return RunResult(p.returncode, (p.stdout or "") + (p.stderr or ""))


def import_project(project: Path) -> RunResult:
    """Imports resources and refreshes the global class cache (required before running scripts)."""
    return run(project, ["--import"], timeout=300)


def run_scene(project: Path, scene: str, user_args: list[str] | None = None, *, import_first: bool = False,
              fixed_fps: int | None = None, timeout: float = 180, check: bool = True) -> RunResult:
    if import_first:
        import_project(project)
    args: list[str] = []
    if fixed_fps:
        args += ["--fixed-fps", str(fixed_fps)]
    args.append(scene)
    if user_args:
        args += ["--", *user_args]
    result = run(project, args, timeout=timeout)
    if check and (result.returncode != 0 or result.script_errors):
        raise GodotError(f"Godot failed running {scene} (exit {result.returncode})", result.output)
    return result


_ERR = re.compile(r"^(SCRIPT ERROR|ERROR|USER ERROR|Parse Error|Compile Error)\b.*", re.MULTILINE)


def find_errors(output: str) -> list[str]:
    errors = []
    for m in _ERR.finditer(output):
        line = m.group(0)
        if any(n in line for n in _NOISE):
            continue
        errors.append(line.strip())
    return errors
