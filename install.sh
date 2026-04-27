#!/usr/bin/env bash
# Claudio — Claude Code Sound Notifications
# https://github.com/Liam-Griffiths/claudio
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "  ♪  C L A U D I O"
echo "  Claude Code Sound Notifications"
echo "  https://github.com/Liam-Griffiths/claudio"
echo ""

# ── Dependencies ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "✗  python3 is required but not found." >&2
  exit 1
fi

# ── Copy files ────────────────────────────────────────────────────────────────
mkdir -p "$HOOKS_DIR"

cp "$SCRIPT_DIR/hooks/notify_sound.py" "$HOOKS_DIR/notify_sound.py"
cp "$SCRIPT_DIR/hooks/sound_tui.py"    "$HOOKS_DIR/sound_tui.py"
chmod +x "$HOOKS_DIR/notify_sound.py" "$HOOKS_DIR/sound_tui.py"

echo "  ✓  notify_sound.py"
echo "  ✓  sound_tui.py"

# ── Merge settings.json ───────────────────────────────────────────────────────
NEW_HOOKS=$(cat <<'EOF'
{
  "Stop":         [{"hooks": [{"type": "command", "command": "python3 \"$HOME/.claude/hooks/notify_sound.py\" Stop",         "async": true, "timeout": 5}]}],
  "Notification": [{"hooks": [{"type": "command", "command": "python3 \"$HOME/.claude/hooks/notify_sound.py\" Notification", "async": true, "timeout": 5}]}],
  "StopFailure":  [{"hooks": [{"type": "command", "command": "python3 \"$HOME/.claude/hooks/notify_sound.py\" StopFailure",  "async": true, "timeout": 5}]}]
}
EOF
)

mkdir -p "$HOME/.claude"

if [[ -f "$SETTINGS" ]]; then
  echo ""
  echo "  Merging into existing settings.json…"
  python3 - "$SETTINGS" "$NEW_HOOKS" <<'PYEOF'
import json, sys

path     = sys.argv[1]
new_h    = json.loads(sys.argv[2])

with open(path) as f:
    cfg = json.load(f)

hooks = cfg.setdefault("hooks", {})
merged, skipped = [], []

for event, entries in new_h.items():
    if event not in hooks:
        hooks[event] = entries
        merged.append(event)
    else:
        # Check if a claudio command is already registered
        already = any(
            "notify_sound.py" in h.get("command", "")
            for group in hooks[event]
            for h in group.get("hooks", [])
        )
        if not already:
            hooks[event].extend(entries)
            merged.append(event)
        else:
            skipped.append(event)

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)

if merged:
    print(f"  ✓  Added hooks: {', '.join(merged)}")
if skipped:
    print(f"  ↩  Already present, skipped: {', '.join(skipped)}")
PYEOF
else
  python3 - "$SETTINGS" "$NEW_HOOKS" <<'PYEOF'
import json, sys

path  = sys.argv[1]
hooks = json.loads(sys.argv[2])
cfg   = {"hooks": hooks}

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)

print("  ✓  Created settings.json")
PYEOF
fi

# ── Smoke test ────────────────────────────────────────────────────────────────
echo ""
echo "  Testing sounds (you should hear 3 tones)…"
python3 "$HOOKS_DIR/notify_sound.py" Notification 2>/dev/null && sleep 0.4 || true
python3 "$HOOKS_DIR/notify_sound.py" Stop         2>/dev/null && sleep 0.5 || true
python3 "$HOOKS_DIR/notify_sound.py" StopFailure  2>/dev/null           || true

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "  ✓  Claudio installed successfully."
echo ""
echo "  Restart Claude Code for hooks to take effect."
echo ""
echo "  Open the TUI:"
echo "    python3 ~/.claude/hooks/sound_tui.py"
echo ""
