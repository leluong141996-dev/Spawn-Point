"""`spawnpoint llm up|down|status`: run SpawnPoint-Coder-7B locally.

Two backends: vLLM in Docker on an NVIDIA GPU (AWQ, fastest), or Ollama anywhere else (GGUF Q4_K_M:
Apple Silicon, AMD, or plain CPU). `auto` picks vLLM when Docker and an NVIDIA GPU are present.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

NAME = os.environ.get("SPAWNPOINT_LLM_CONTAINER", "spawnpoint-llm")
IMAGE = os.environ.get("VLLM_IMAGE", "vllm/vllm-openai:v0.10.2")  # CUDA 12.8: NVIDIA driver >= 570
DEFAULT_MODEL = "smoky1496/SpawnPoint-Coder-7B-AWQ"
MODEL = os.environ.get("SPAWNPOINT_MODEL", DEFAULT_MODEL)
# This Spawn Point version speaks the v5 per-genre format: pin the weights that do, whatever the repo's main becomes.
REVISION = os.environ.get("SPAWNPOINT_MODEL_REVISION") or ("v5.1-release" if MODEL == DEFAULT_MODEL else "")
SERVED = "SpawnPoint-Coder-7B"
OLLAMA_MODEL = os.environ.get("SPAWNPOINT_OLLAMA_MODEL", "hf.co/smoky1496/SpawnPoint-Coder-7B-GGUF:Q4_K_M")
OLLAMA_PORT = 11434


def pick_backend(choice: str = "auto") -> str:
    if choice != "auto":
        return choice
    if shutil.which("docker") and shutil.which("nvidia-smi"):
        return "vllm"
    if shutil.which("ollama"):
        return "ollama"
    raise RuntimeError("no local backend found: install Ollama (https://ollama.com/download) on any machine, "
                       "or Docker + the NVIDIA container toolkit for vLLM. A hosted API works too: "
                       "set SPAWNPOINT_LLM_BASE_URL / SPAWNPOINT_LLM_MODEL / SPAWNPOINT_LLM_API_KEY.")


def _ollama(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["ollama", *args], capture_output=capture, text=True)


def ollama_up(say=print) -> int:
    if _ollama("list").returncode != 0:
        say("Ollama is installed but its server is not running: start the Ollama app or run `ollama serve`.")
        return 1
    say(f"Pulling {OLLAMA_MODEL} with Ollama (first time ~4.7 GB) ...")
    if _ollama("pull", OLLAMA_MODEL, capture=False).returncode != 0:
        return 1
    say(f"Ready: http://localhost:{OLLAMA_PORT}/v1 (model {OLLAMA_MODEL}). Spawn Point finds it automatically.")
    return 0


def _docker(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is required (with the NVIDIA container toolkit) to run the local model")
    return subprocess.run(["docker", *args], check=check, capture_output=capture, text=True)


def _exists() -> bool:
    return bool(_docker("ps", "-a", "--filter", f"name=^{NAME}$", "--format", "{{.Names}}").stdout.strip())


def _running() -> bool:
    out = _docker("inspect", "-f", "{{.State.Running}}", NAME, check=False)
    return out.returncode == 0 and out.stdout.strip() == "true"


def ready(port: int = 8000) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/v1/models", timeout=2)
        return True
    except Exception:
        return False


def up(port: int = 8000, max_len: int = 16384, say=print, backend: str = "auto") -> int:
    if pick_backend(backend) == "ollama":
        return ollama_up(say)
    if _exists():
        _docker("start", NAME)
    else:
        hf = Path.home() / ".cache" / "huggingface"
        hf.mkdir(parents=True, exist_ok=True)
        user = getpass.getuser()
        # Run as the current user so downloaded weights are not root-owned; that UID does not exist in
        # the image, so USER/LOGNAME are set for torch's getpass.getuser().
        _docker("run", "-d", "--name", NAME, "--gpus", "all", "-p", f"{port}:8000", "--ipc=host",
                "-u", f"{os.getuid()}:{os.getgid()}", "-e", f"USER={user}", "-e", f"LOGNAME={user}",
                "-e", "HOME=/tmp", "-e", "HF_HOME=/hf", "-v", f"{hf}:/hf", IMAGE, "--model", MODEL,
                *(["--revision", REVISION] if REVISION else []), "--served-model-name", SERVED, "--max-model-len", str(max_len), "--gpu-memory-utilization", "0.85")
    say(f"Starting {SERVED} on :{port} (first start downloads ~5.6 GB) ...")
    while not ready(port):
        if not _running():
            say(_docker("logs", "--tail", "30", NAME, check=False).stdout)
            return 1
        time.sleep(2)
    say(f"Ready: http://localhost:{port}/v1 — stop with `spawnpoint llm down`.")
    return 0


def down(say=print, backend: str = "auto") -> int:
    if pick_backend(backend) == "ollama":
        _ollama("stop", OLLAMA_MODEL)
        say("Unloaded from Ollama.")
    elif _exists():
        _docker("stop", NAME)
        say("Stopped.")
    else:
        say("Not running.")
    return 0


def status(port: int = 8000, say=print, backend: str = "auto") -> int:
    if pick_backend(backend) == "ollama":
        have = OLLAMA_MODEL.split(":")[0].lower() in _ollama("list").stdout.lower()
        say(f"Ollama model {OLLAMA_MODEL}: {'pulled' if have else 'not pulled'}; "
            f"API on :{OLLAMA_PORT}: {'ready' if ready(OLLAMA_PORT) else 'not responding'}")
        return 0
    say(f"container {NAME}: {'running' if _exists() and _running() else 'stopped'}; "
        f"API on :{port}: {'ready' if ready(port) else 'not responding'}")
    return 0
