#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
PYTHON="$ROOT/.venv/bin/python"
MODE_FILE="$ROOT/artifacts/ap01-mode"
CUSTOM_GIF="$ROOT/artifacts/custom-screen.gif"

mode="quota"
if [[ -f "$MODE_FILE" ]]; then
    mode="$(tr -d '[:space:]' < "$MODE_FILE")"
fi

cd "$ROOT"
if [[ "$mode" == "custom" && -f "$CUSTOM_GIF" ]]; then
    echo "AP01 mode: custom ($CUSTOM_GIF)"
    exec "$PYTHON" -u "$ROOT/ap01_screen_bridge.py" \
        "$CUSTOM_GIF" --bind 0.0.0.0 --port 8765
fi

echo "AP01 mode: quota"
exec "$PYTHON" -u "$ROOT/ap01_wifi_bridge.py" \
    --bind 0.0.0.0 --port 8765 --interval 300
