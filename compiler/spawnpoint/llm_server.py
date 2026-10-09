"""`spawnpoint llm up|down|status`: run SpawnPoint-Coder-7B locally in the vLLM Docker image."""

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
MODEL = os.environ.get("SPAWNPOINT_MODEL", "smoky1496/SpawnPoint-Coder-7B-AWQ")
SERVED = "SpawnPoint-Coder-7B"


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


def up(port: int = 8000, max_len: int = 16384, say=print) -> int:
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
                "--served-model-name", SERVED, "--max-model-len", str(max_len), "--gpu-memory-utilization", "0.85")
    say(f"Starting {SERVED} on :{port} (first start downloads ~5.6 GB) ...")
    while not ready(port):
        if not _running():
            say(_docker("logs", "--tail", "30", NAME, check=False).stdout)
            return 1
        time.sleep(2)
    say(f"Ready: http://localhost:{port}/v1 — stop with `spawnpoint llm down`.")
    return 0


def down(say=print) -> int:
    if _exists():
        _docker("stop", NAME)
        say("Stopped.")
    else:
        say("Not running.")
    return 0


def status(port: int = 8000, say=print) -> int:
    say(f"container {NAME}: {'running' if _exists() and _running() else 'stopped'}; "
        f"API on :{port}: {'ready' if ready(port) else 'not responding'}")
    return 0
