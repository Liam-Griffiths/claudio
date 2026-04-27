#!/usr/bin/env python3
"""
Claude Code Sound Hook Runner
Called by Claude Code hooks: notify_sound.py <event>
Event names: Stop | Notification | StopFailure  (or: done | notify | error)
"""

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "hooks" / "sound_config.json"

# Normalise short names used by legacy shell invocations
EVENT_ALIAS = {
    "done":  "Stop",
    "notify": "Notification",
    "error":  "StopFailure",
}

BUILTIN_NOTES = {
    "builtin:done":    [(880, 0.12), (1046, 0.20)],
    "builtin:notify":  [(660, 0.18)],
    "builtin:error":   [(440, 0.14), (330, 0.22)],
    "builtin:chime":   [(523, 0.10), (659, 0.10), (784, 0.20)],
    "builtin:blip":    [(1200, 0.06)],
    "builtin:success": [(523, 0.10), (659, 0.10), (784, 0.10), (1046, 0.25)],
}

DEFAULT_CONFIG = {
    "enabled": True,
    "volume":  0.6,
    "events": {
        "Stop":         {"sound": "builtin:success", "enabled": True},
        "Notification": {"sound": "builtin:notify", "enabled": True},
        "StopFailure":  {"sound": "builtin:error",  "enabled": True},
    },
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return DEFAULT_CONFIG


def make_wav(notes, volume):
    rate, samples = 44100, []
    for freq, dur in notes:
        n = int(rate * dur)
        fade = max(1, int(n * 0.15))
        for i in range(n):
            v = math.sin(2 * math.pi * freq * i / rate)
            if i >= n - fade:
                v *= 1 - (i - (n - fade)) / fade
            samples.append(int(v * volume * 32767))
        samples.extend([0] * int(rate * 0.025))
    data = struct.pack(f"<{len(samples)}h", *samples)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(data)
    return tmp.name


def detect_player():
    """Return (cmd, extra_args, handles_mp3) or None."""
    import platform
    if platform.system() == "Darwin":
        return ("afplay", [], True)
    for p, extra, mp3 in [
        ("paplay",  [],                                               False),
        ("pw-play", [],                                               False),
        ("ffplay",  ["-nodisp", "-autoexit", "-loglevel", "quiet"],  True),
        ("mpg123",  ["-q"],                                           True),
        ("mpg321",  [],                                               True),
        ("aplay",   ["-q"],                                           False),
        ("vlc",     ["--intf", "dummy", "--play-and-exit", "-q"],    True),
    ]:
        if subprocess.run(["which", p], capture_output=True).returncode == 0:
            return (p, extra, mp3)
    return None


def play(sound_id, volume):
    pl = detect_player()
    if pl is None:
        return

    cmd, extra, handles_mp3 = pl

    if sound_id.startswith("builtin:"):
        notes = BUILTIN_NOTES.get(sound_id, BUILTIN_NOTES["builtin:notify"])
        wav = make_wav(notes, volume)
        subprocess.run([cmd] + extra + [wav], capture_output=True)
        os.unlink(wav)
        return

    path = Path(sound_id)
    if not path.exists():
        return

    if path.suffix.lower() == ".mp3" and not handles_mp3:
        # Fallback: find an mp3-capable player
        for p, ex, _ in [
            ("mpg123",  ["-q"]),
            ("mpg321",  []),
            ("ffplay",  ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
            ("vlc",     ["--intf", "dummy", "--play-and-exit", "-q"]),
        ]:
            if subprocess.run(["which", p], capture_output=True).returncode == 0:
                subprocess.run([p] + ex + [str(path)], capture_output=True)
                return
    else:
        subprocess.run([cmd] + extra + [str(path)], capture_output=True)


def main():
    raw_event = sys.argv[1] if len(sys.argv) > 1 else "Stop"
    event     = EVENT_ALIAS.get(raw_event, raw_event)

    cfg     = load_config()
    volume  = float(cfg.get("volume", 0.6))

    # Global kill-switch
    if not cfg.get("enabled", True):
        sys.exit(0)

    ev_cfg  = cfg.get("events", {}).get(event, {})
    if not ev_cfg.get("enabled", True):
        sys.exit(0)

    sound_id = ev_cfg.get("sound", "builtin:notify")
    play(sound_id, volume)


if __name__ == "__main__":
    main()