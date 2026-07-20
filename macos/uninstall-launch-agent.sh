#!/bin/zsh
set -euo pipefail

LABEL="io.github.wqytommy666.cuktech-screen-controller.bridge"
TARGET="$HOME/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
if [[ -f "$TARGET" ]]; then
    mv "$TARGET" "$HOME/.Trash/${LABEL}.plist.$(date +%s)"
fi
echo "Removed $LABEL"
