# ♪ Claudio

**Sound notifications for [Claude Code](https://claude.ai/code) — hear a ping when Claude is done.**

Claudio hooks into Claude Code's lifecycle events and plays audio cues so you can look away and get notified when it finishes. Comes with a full terminal UI to configure sounds, volume, and per-event settings.

```bash
git clone https://github.com/Liam-Griffiths/claudio && bash claudio/install.sh
```

---

## TUI

Open the configurator at any time:

```bash
python3 ~/.claude/hooks/sound_tui.py
```

```
  ♪  CLAUDE CODE  ·  SOUND NOTIFICATIONS
  ─────────────────────────────────────────────────────────────
  [● SOUNDS ON ]   Space · toggle all
   Volume  [████████████░░░░░░░░]  60%   ← → to adjust
  ─────────────────────────────────────────────────────────────
  EVENTS

▶ ● Task Complete        Claude finished a response
    ◄  Ding Dong  ►      ← → cycle  F pick file  T test  S toggle

  ● Needs Attention      Claude needs your input
     Single Ping

  ● Error Occurred       Claude hit a problem
     Descending
  ─────────────────────────────────────────────────────────────
  W save   Q quit   T test   F file picker   S toggle event
```

### Controls

| Key | Action |
|---|---|
| `↑` `↓` | Move between rows |
| `←` `→` | Cycle built-in sounds / adjust volume |
| `T` | Preview the selected sound |
| `F` | Open file browser — pick any MP3, WAV, etc. |
| `S` | Toggle an individual event on/off |
| `Space` | Toggle all sounds on/off |
| `W` | Save |
| `Q` | Save and quit |

---

## Events

| Claude Code Hook | Default Sound | When it fires |
|---|---|---|
| `Stop` | Ding Dong | Claude finished a response |
| `Notification` | Single Ping | Claude needs your attention |
| `StopFailure` | Descending | Claude hit an error |

---

## Built-in sounds

| Name | Description |
|---|---|
| Ding Dong | Two-note ascending chime |
| Single Ping | Clean single note |
| Descending | Two-note falling tone |
| Triple Chime | Three-note ascending sequence |
| Short Blip | Quick electronic beep |
| Success | Uplifting four-note resolution |

---

## Custom sounds & MP3

Press `F` on any event row to browse your filesystem and pick a file. Press `T` in the browser to preview before selecting.

**Supported formats:** `.mp3` `.wav` `.aiff` `.ogg` `.flac` `.m4a`

**MP3 on Linux** requires one of: `mpg123`, `mpg321`, `ffplay`, or `vlc`.  
macOS handles every format natively via `afplay` — no extra installs needed.

---

## Platform support

| Platform | Player |
|---|---|
| macOS | `afplay` (built-in) |
| Linux / PulseAudio | `paplay` |
| Linux / PipeWire | `pw-play` |
| Linux / ALSA | `aplay` |
| Linux / generic | `ffplay` or `vlc` |

---

## How it works

Claudio uses [Claude Code hooks](https://docs.claude.com/en/claude-code/hooks) — deterministic shell commands that fire at lifecycle events regardless of what the model decides to do.

The install script adds three async hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop":         [{ "hooks": [{ "type": "command", "command": "python3 \"$HOME/.claude/hooks/notify_sound.py\" Stop",         "async": true }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "python3 \"$HOME/.claude/hooks/notify_sound.py\" Notification", "async": true }] }],
    "StopFailure":  [{ "hooks": [{ "type": "command", "command": "python3 \"$HOME/.claude/hooks/notify_sound.py\" StopFailure",  "async": true }] }]
  }
}
```

All hooks are `async: true` so they never block Claude's execution. Your preferences are stored in `~/.claude/hooks/sound_config.json`.

---

## Files installed

```
~/.claude/
├── settings.json              ← Claude Code hook config (merged, not replaced)
└── hooks/
    ├── notify_sound.py        ← Hook runner
    ├── sound_tui.py           ← TUI configurator
    └── sound_config.json      ← Your settings (created on first TUI save)
```

---

## Uninstall

```bash
bash claudio/uninstall.sh
```

---

## Requirements

- Python 3
- Claude Code
- An audio player (see platform table above)
