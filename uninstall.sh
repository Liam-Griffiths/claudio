#!/usr/bin/env bash
# Claudio uninstaller
set -e

HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "  ♪  Claudio — Uninstaller"
echo ""

# Remove scripts
for f in notify_sound.py sound_tui.py sound_config.json; do
  fp="$HOOKS_DIR/$f"
  if [[ -f "$fp" ]]; then
    rm "$fp"
    echo "  ✓  Removed $fp"
  fi
done

# Remove hooks from settings.json
if [[ -f "$SETTINGS" ]] && command -v python3 &>/dev/null; then
  python3 - "$SETTINGS" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

hooks = cfg.get("hooks", {})
removed = []

for event in list(hooks.keys()):
    before = len(hooks[event])
    hooks[event] = [
        group for group in hooks[event]
        if not any("notify_sound.py" in h.get("command", "")
                   for h in group.get("hooks", []))
    ]
    if len(hooks[event]) < before:
        removed.append(event)
    if not hooks[event]:
        del hooks[event]

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)

if removed:
    print(f"  ✓  Removed hooks from settings.json: {', '.join(removed)}")
else:
    print("  ↩  No Claudio hooks found in settings.json")
PYEOF
fi

echo ""
echo "  ✓  Claudio uninstalled."
echo ""
