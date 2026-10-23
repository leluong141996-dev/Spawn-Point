"""`spawnpoint setup`: everything a new user needs, checked and (where possible) installed for them.

- Godot 4.6, downloaded from the official GitHub release into Spawn Point's own folder when none is found;
- the Godot web export templates, of which only the two web files are fetched out of the 1 GB template archive
  (the archive is a zip: its directory and the two members are read with HTTP range requests, about 80 MB);
- a way to run the model: an NVIDIA GPU with Docker (vLLM), Ollama, or an OpenAI-compatible API.
"""

from __future__ import annotations

import io
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

GODOT_VERSION = "4.6.2"
RELEASE_URL = f"https://github.com/godotengine/godot/releases/download/{GODOT_VERSION}-stable"
TEMPLATES_TAG = f"{GODOT_VERSION}.stable"  # the folder name Godot looks for
WEB_TEMPLATES = ("web_nothreads_release.zip", "web_nothreads_debug.zip")  # single-threaded: no COOP/COEP needed


def data_dir() -> Path:
    """Spawn Point's own folder for downloaded tools."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "spawnpoint"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "spawnpoint"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "spawnpoint"


def templates_dir() -> Path:
    """Where Godot looks for export templates of this version."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Godot"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Godot"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "godot"
    return base / "export_templates" / TEMPLATES_TAG


def godot_asset(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """(release file, the Godot binary inside it) for this computer."""
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    v = f"Godot_v{GODOT_VERSION}-stable"
    if system == "Darwin":
        return f"{v}_macos.universal.zip", "Godot.app/Contents/MacOS/Godot"
    if system == "Windows":
        return f"{v}_win64.exe.zip", f"{v}_win64_console.exe"  # the console build prints to the terminal
    arch = "arm64" if machine in ("aarch64", "arm64") else "x86_64"
    return f"{v}_linux.{arch}.zip", f"{v}_linux.{arch}"


def managed_binary() -> Path:
    """The Godot binary `spawnpoint setup` installs (it may not exist yet)."""
    return data_dir() / f"godot-{GODOT_VERSION}" / godot_asset()[1]


# --- downloads ------------------------------------------------------------------------------------------------

class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable view of a remote file, read with HTTP range requests (enough for zipfile)."""

    def __init__(self, url: str, block: int = 1 << 20):
        super().__init__()
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.url = r.geturl()  # follow GitHub's redirect once
            self.size = int(r.headers["Content-Length"])
            if r.headers.get("Accept-Ranges", "bytes") != "bytes":
                raise OSError("the server does not support range requests")
        self.pos = 0
        self.block = block
        self._cache: dict[int, bytes] = {}

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def _get_block(self, i: int) -> bytes:
        if i not in self._cache:
            start, end = i * self.block, min(self.size, (i + 1) * self.block) - 1
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                self._cache[i] = r.read()
            if len(self._cache) > 64:  # keep memory bounded: members are read front to back
                self._cache.pop(next(iter(self._cache)))
        return self._cache[i]

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            i, off = divmod(self.pos, self.block)
            chunk = self._get_block(i)[off:off + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def _download(url: str, dest: Path, say) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done, shown = 0, -1
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            pct = done * 100 // total if total else 0
            if pct // 10 != shown:
                shown = pct // 10
                say(f"    {done / 1e6:.0f} / {total / 1e6:.0f} MB")
    tmp.replace(dest)


def install_godot(say=print) -> Path:
    asset, inner = godot_asset()
    folder = data_dir() / f"godot-{GODOT_VERSION}"
    target = folder / inner
    if target.exists():
        return target
    archive = data_dir() / asset
    say(f"  downloading Godot {GODOT_VERSION} ({asset}) ...")
    _download(f"{RELEASE_URL}/{asset}", archive, say)
    with zipfile.ZipFile(archive) as z:
        z.extractall(folder)
    archive.unlink()
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def web_templates_ready() -> bool:
    return all((templates_dir() / f).exists() for f in WEB_TEMPLATES)


def install_web_templates(say=print, url: str | None = None) -> Path:
    """Fetches only the web templates out of the official template archive."""
    out = templates_dir()
    if web_templates_ready():
        return out
    out.mkdir(parents=True, exist_ok=True)
    url = url or f"{RELEASE_URL}/Godot_v{GODOT_VERSION}-stable_export_templates.tpz"
    say("  fetching the web export templates (about 80 MB of the 1 GB archive) ...")
    try:
        z = zipfile.ZipFile(HttpRangeFile(url))
    except OSError:  # no range requests: download the whole archive once
        archive = data_dir() / "templates.tpz"
        _download(url, archive, say)
        z = zipfile.ZipFile(archive)
    with z:
        for member in WEB_TEMPLATES + ("version.txt",):
            name = f"templates/{member}"
            with z.open(name) as src, open(out / member, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            say(f"    {member}")
    return out


# --- the model ---------------------------------------------------------------------------------------------------

@dataclass
class LLMCheck:
    nvidia: bool
    docker: bool
    ollama: bool
    api: bool  # SPAWNPOINT_LLM_BASE_URL points somewhere

    def backend(self) -> str | None:
        if self.api:
            return "api"
        if self.nvidia and self.docker:
            return "vllm"
        if self.ollama:
            return "ollama"
        return None


def _runs(cmd: list[str]) -> bool:
    if not shutil.which(cmd[0]):
        return False
    try:
        return subprocess.run(cmd, capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def check_llm() -> LLMCheck:
    return LLMCheck(nvidia=_runs(["nvidia-smi"]), docker=_runs(["docker", "info"]), ollama=bool(shutil.which("ollama")),
                    api=bool(os.environ.get("SPAWNPOINT_LLM_BASE_URL")))


# --- the command -------------------------------------------------------------------------------------------------

def run(args) -> int:
    from . import godot

    say = print
    ok = True
    say("Spawn Point setup\n")
    # 1. Godot
    try:
        binary = godot.find_binary()
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        if not version.startswith("4."):
            raise godot.GodotError(f"found Godot {version or '?'}, Spawn Point needs Godot 4")
        say(f"✓ Godot {version.split('.stable')[0]} ({binary})")
    except (godot.GodotError, OSError, subprocess.TimeoutExpired) as e:
        if args.check:
            say(f"✗ Godot 4: {e}")
            ok = False
        else:
            binary = str(install_godot(say))
            say(f"✓ Godot {GODOT_VERSION} installed ({binary})")
    # 2. Web templates (to play and share games in the browser)
    if web_templates_ready():
        say(f"✓ web export templates ({templates_dir()})")
    elif args.check or args.no_web:
        say("✗ web export templates: run `spawnpoint setup` to fetch them (needed to play in the browser and share)")
        ok = ok and args.no_web
    else:
        install_web_templates(say)
        say(f"✓ web export templates installed ({templates_dir()})")
    # 3. The model
    llm = check_llm()
    backend = llm.backend()
    if getattr(args, "no_model", False):
        backend = "skip"
    elif backend == "api":
        say(f"✓ model: an OpenAI-compatible API at {os.environ['SPAWNPOINT_LLM_BASE_URL']}")
    elif backend == "vllm":
        say("✓ model: NVIDIA GPU and Docker found; `spawnpoint llm up` serves SpawnPoint-Coder-7B with vLLM")
    elif backend == "ollama":
        say("✓ model: Ollama found; `spawnpoint llm up` pulls SpawnPoint-Coder-7B (GGUF, about 4.7 GB)")
    elif backend is None:
        say("✗ model: no way to run it yet. Install Ollama (https://ollama.com/download, any computer)"
            " or Docker with an NVIDIA GPU, then run `spawnpoint setup` again.")
        ok = False
    say("")
    if ok:
        say("Ready. Make your first game:")
        if backend in ("vllm", "ollama"):
            say("  spawnpoint llm up")
        say('  spawnpoint create "a ninja platformer where you collect stars"')
    else:
        say("Not ready yet: fix the ✗ lines above.")
    return 0 if ok else 1
