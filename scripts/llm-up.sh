#!/usr/bin/env bash
# Start a local OpenAI-compatible LLM for Spawn Point:
# SpawnPoint-Coder-7B (AWQ 4-bit, ~11 GB VRAM, 16k context) served by vLLM on http://localhost:8000/v1.
# Override with MODEL=..., VLLM_IMAGE=..., MAX_LEN=..., PORT=...
set -euo pipefail

NAME=${SPAWNPOINT_LLM_CONTAINER:-spawnpoint-llm}
IMAGE=${VLLM_IMAGE:-vllm/vllm-openai:v0.10.2}   # CUDA 12.8 — works with NVIDIA driver 570
MODEL=${MODEL:-smoky1496/SpawnPoint-Coder-7B-AWQ}
MAX_LEN=${MAX_LEN:-16384}
PORT=${PORT:-8000}

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker start "$NAME" >/dev/null
else
  # Runs as the current user so downloaded weights are not root-owned; USER/LOGNAME are needed
  # because that UID does not exist inside the image (torch calls getpass.getuser()).
  docker run -d --name "$NAME" --gpus all -p "$PORT:8000" --ipc=host \
    -u "$(id -u):$(id -g)" -e USER="$(whoami)" -e LOGNAME="$(whoami)" -e HOME=/tmp -e HF_HOME=/hf \
    -v "$HOME/.cache/huggingface:/hf" \
    "$IMAGE" --model "$MODEL" --served-model-name SpawnPoint-Coder-7B --max-model-len "$MAX_LEN" \
    --gpu-memory-utilization 0.85 >/dev/null
fi

echo -n "Waiting for $MODEL on :$PORT "
until curl -sf "localhost:$PORT/v1/models" >/dev/null; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" != "true" ]; then
    echo; echo "The container stopped. Logs:"; docker logs --tail 30 "$NAME"; exit 1
  fi
  echo -n "."; sleep 2
done
echo " ready. Stop it with: docker stop $NAME"
