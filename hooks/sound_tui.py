#!/usr/bin/env python3
"""
Claude Code Sound Notifications — TUI Configurator
Navigate with ↑↓, adjust with ←→, press T to test, F to pick file, W to save.
"""

import curses
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".claude" / "hooks" / "sound_config.json"
AUDIO_EXTS  = {".mp3", ".wav", ".aiff", ".aif", ".ogg", ".flac", ".m4a"}

BUILTIN_SOUNDS = [
    ("builtin:done",    "Ding Dong",     [(880, 0.12), (1046, 0.20)]),
    ("builtin:notify",  "Single Ping",   [(660, 0.18)]),
    ("builtin:error",   "Descending",    [(440, 0.14), (330, 0.22)]),
    ("builtin:chime",   "Triple Chime",  [(523, 0.10), (659, 0.10), (784, 0.20)]),
    ("builtin:blip",    "Short Blip",    [(1200, 0.06)]),
    ("builtin:success", "Success",       [(523, 0.10), (659, 0.10), (784, 0.10), (1046, 0.25)]),
]
BUILTIN_IDS  = [s[0] for s in BUILTIN_SOUNDS]
BUILTIN_MAP  = {s[0]: s for s in BUILTIN_SOUNDS}

EVENTS = [
    ("Stop",         "Task Complete",   "Claude finished a response"),
    ("Notification", "Needs Attention", "Claude needs your input"),
    ("StopFailure",  "Error Occurred",  "Claude hit a problem"),
]

DEFAULT_CONFIG = {
    "enabled": True,
    "volume":  0.6,
    "min_duration_secs": 30,
    "events": {
        "Stop":         {"sound": "builtin:success", "enabled": True},
        "Notification": {"sound": "builtin:notify", "enabled": True},
        "StopFailure":  {"sound": "builtin:error",  "enabled": True},
    },
}


def fmt_duration(secs):
    if secs == 0:
        return "Always"
    m, s = divmod(int(secs), 60)
    if m == 0:
        return f"{s}s"
    return f"{m}m" if s == 0 else f"{m}m {s}s"

# ── Color pair IDs ─────────────────────────────────────────────────────────────
CP_NORMAL   = 1
CP_TITLE    = 2
CP_SEL      = 3
CP_ACCENT   = 4
CP_DIM      = 5
CP_GREEN    = 6
CP_RED      = 7
CP_YELLOW   = 8


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_NORMAL,  curses.COLOR_WHITE,  -1)
    curses.init_pair(CP_TITLE,   curses.COLOR_CYAN,   -1)
    curses.init_pair(CP_SEL,     curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP_ACCENT,  curses.COLOR_CYAN,   -1)
    curses.init_pair(CP_DIM,     curses.COLOR_WHITE,  -1)   # will use A_DIM
    curses.init_pair(CP_GREEN,   curses.COLOR_GREEN,  -1)
    curses.init_pair(CP_RED,     curses.COLOR_RED,    -1)
    curses.init_pair(CP_YELLOW,  curses.COLOR_YELLOW, -1)


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _make_wav(notes, volume):
    rate = 44100
    samples = []
    for freq, dur in notes:
        n = int(rate * dur)
        fade = max(1, int(n * 0.15))
        for i in range(n):
            v = math.sin(2 * math.pi * freq * i / rate)
            if i >= n - fade:
                v *= 1 - (i - (n - fade)) / fade
            samples.append(int(v * volume * 32767))
        samples.extend([0] * int(rate * 0.025))   # tiny gap between notes
    data = struct.pack(f"<{len(samples)}h", *samples)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(data)
    return tmp.name


def _detect_player():
    import platform
    if platform.system() == "Darwin":
        return ("afplay", [], True)   # (cmd, extra_args, handles_mp3)
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


_player_cache = None

def get_player():
    global _player_cache
    if _player_cache is None:
        _player_cache = _detect_player()
    return _player_cache


def play_sound(sound_id, volume=0.6):
    """Play builtin: or file path. Non-blocking."""
    def _play():
        try:
            pl = get_player()
            if pl is None:
                return
            cmd, extra, handles_mp3 = pl

            if sound_id.startswith("builtin:"):
                info = BUILTIN_MAP.get(sound_id)
                if not info:
                    return
                wav = _make_wav(info[2], volume)
                subprocess.run([cmd] + extra + [wav], capture_output=True)
                os.unlink(wav)
            else:
                path = Path(sound_id)
                if not path.exists():
                    return
                if path.suffix.lower() == ".mp3" and not handles_mp3:
                    # Try a dedicated mp3 player
                    for p, ex, _ in [("mpg123", ["-q"], True), ("mpg321", [], True),
                                     ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"], True)]:
                        if subprocess.run(["which", p], capture_output=True).returncode == 0:
                            subprocess.run([p] + ex + [str(path)], capture_output=True)
                            return
                else:
                    subprocess.run([cmd] + extra + [str(path)], capture_output=True)
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()


# ── Config I/O ────────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            cfg = dict(DEFAULT_CONFIG)
            cfg.update({k: v for k, v in data.items() if k != "events"})
            cfg["events"] = dict(DEFAULT_CONFIG["events"])
            for ev, defaults in DEFAULT_CONFIG["events"].items():
                if ev in data.get("events", {}):
                    cfg["events"][ev] = {**defaults, **data["events"][ev]}
            return cfg
        except Exception:
            pass
    return {**DEFAULT_CONFIG, "events": {k: dict(v) for k, v in DEFAULT_CONFIG["events"].items()}}


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ── File browser modal ────────────────────────────────────────────────────────

def file_browser(stdscr, start=None):
    """Returns selected file path string, or None if cancelled."""
    cwd    = Path(start or Path.home())
    cursor = 0
    scroll = 0

    def ls(path):
        items = []
        if path.parent != path:
            items.append(("up", path.parent))
        try:
            for e in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if e.is_dir():
                    items.append(("dir", e))
                elif e.suffix.lower() in AUDIO_EXTS:
                    items.append(("file", e))
        except PermissionError:
            pass
        return items

    items = ls(cwd)

    h, w   = stdscr.getmaxyx()
    mh     = min(22, h - 2)
    mw     = min(72, w - 4)
    my     = (h - mh) // 2
    mx     = (w - mw) // 2
    list_h = mh - 5
    win    = curses.newwin(mh, mw, my, mx)
    win.keypad(True)

    while True:
        h, w    = stdscr.getmaxyx()
        new_mh  = min(22, h - 2)
        new_mw  = min(72, w - 4)
        if new_mh != mh or new_mw != mw:
            mh, mw  = new_mh, new_mw
            my      = (h - mh) // 2
            mx      = (w - mw) // 2
            list_h  = mh - 5
            win     = curses.newwin(mh, mw, my, mx)
            win.keypad(True)

        win.erase()
        win.attron(curses.color_pair(CP_TITLE))
        win.box()
        win.attroff(curses.color_pair(CP_TITLE))

        ttl = " ♪  SELECT SOUND FILE "
        win.addstr(0, (mw - len(ttl)) // 2, ttl,
                   curses.color_pair(CP_TITLE) | curses.A_BOLD)

        # Current path
        ps = str(cwd)
        if len(ps) > mw - 4:
            ps = "…" + ps[-(mw - 7):]
        win.addstr(1, 2, ps, curses.color_pair(CP_DIM) | curses.A_DIM)

        # Separator
        win.addstr(2, 1, "─" * (mw - 2), curses.color_pair(CP_TITLE) | curses.A_DIM)

        # List
        visible = items[scroll: scroll + list_h]
        for i, (kind, path) in enumerate(visible):
            ri = scroll + i
            sel = ri == cursor
            attr = curses.color_pair(CP_SEL) if sel else curses.color_pair(CP_NORMAL)
            if kind == "up":
                name = "  .."
            elif kind == "dir":
                name = f"  {path.name}/"
                if not sel:
                    attr = curses.color_pair(CP_ACCENT)
            else:
                sz = path.stat().st_size
                kb = f"{sz // 1024:>5} KB" if sz < 1_000_000 else f"{sz // 1_048_576:>4} MB"
                name = f"  ♪  {path.name}"
                # right-align size
                pad = mw - 4 - len(name) - len(kb)
                if pad > 0:
                    name = name + " " * pad + kb
            win.addstr(3 + i, 1, name[:mw - 2].ljust(mw - 2), attr)

        # Help
        win.addstr(mh - 2, 1, "─" * (mw - 2), curses.color_pair(CP_TITLE) | curses.A_DIM)
        help_s = " ↑↓ navigate  Enter select  ← up dir  T preview  Esc cancel"
        win.addstr(mh - 1, 2, help_s[:mw - 3], curses.color_pair(CP_DIM) | curses.A_DIM)

        win.refresh()
        key = win.getch()

        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
            if cursor < scroll:
                scroll = cursor
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(len(items) - 1, cursor + 1)
            if cursor >= scroll + list_h:
                scroll = cursor - list_h + 1
        elif key in (curses.KEY_ENTER, 10, 13):
            if items:
                kind, path = items[cursor]
                if kind in ("dir", "up"):
                    cwd, cursor, scroll = path, 0, 0
                    items = ls(cwd)
                else:
                    return str(path)
        elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8):
            if cwd.parent != cwd:
                cwd, cursor, scroll = cwd.parent, 0, 0
                items = ls(cwd)
        elif key in (ord("t"), ord("T")):
            if items and items[cursor][0] == "file":
                play_sound(str(items[cursor][1]))
        elif key == 27:
            return None


# ── Main draw ─────────────────────────────────────────────────────────────────

def draw(stdscr, cfg, cursor, status, saved):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    def put(y, x, s, attr=0):
        try:
            if 0 <= y < h and 0 <= x < w:
                stdscr.addstr(y, x, s[:w - x - 1], attr)
        except curses.error:
            pass

    # ── Title ──
    title = "  ♪  CLAUDE CODE  ·  SOUND NOTIFICATIONS  "
    pad   = max(0, w - len(title)) * " "
    put(0, 0, title + pad, curses.color_pair(CP_TITLE) | curses.A_BOLD)

    # ── Row 0: Global on/off ──
    y    = 2
    on   = cfg["enabled"]
    icon = "●" if on else "○"
    lbl  = "ON " if on else "OFF"
    c    = CP_GREEN if on else CP_RED
    sel  = cursor == 0
    attr = curses.color_pair(CP_SEL) if sel else (curses.color_pair(c) | curses.A_BOLD)
    put(y, 2, f"[{icon} SOUNDS {lbl}]", attr)
    put(y, 18, "Space · toggle all", curses.color_pair(CP_DIM) | curses.A_DIM)

    # ── Row 1: Volume ──
    y   = 3
    vol = cfg["volume"]
    pct = int(vol * 100)
    bar = "█" * int(20 * vol) + "░" * (20 - int(20 * vol))
    sel = cursor == 1
    attr = curses.color_pair(CP_SEL) if sel else curses.color_pair(CP_YELLOW)
    put(y, 2, f" Volume  [{bar}] {pct:3d}%", attr)
    if sel:
        put(y, 33, "← → adjust", curses.color_pair(CP_DIM) | curses.A_DIM)

    # ── Row 2: Min duration ──
    y     = 4
    min_s = int(cfg.get("min_duration_secs", 60))
    sel   = cursor == 2
    attr  = curses.color_pair(CP_SEL) if sel else curses.color_pair(CP_ACCENT)
    put(y, 2, f" Min dur  ◄ {fmt_duration(min_s):>8} ►", attr)
    hint  = "← → adjust (15s steps)" if sel else "play Stop sound only after this duration"
    put(y, 28, hint, curses.color_pair(CP_DIM) | curses.A_DIM)

    # ── Divider ──
    put(6, 0, "─" * w, curses.color_pair(CP_TITLE) | curses.A_DIM)
    put(7, 2, "EVENTS", curses.color_pair(CP_TITLE) | curses.A_BOLD)
    put(7, 10, "  (↑↓ navigate  ←→ cycle sounds  F pick file  T test  S toggle)", curses.color_pair(CP_DIM) | curses.A_DIM)

    # ── Event rows ──
    y = 8
    for ei, (ev_key, ev_name, ev_desc) in enumerate(EVENTS):
        sel       = cursor == ei + 3
        ev_cfg    = cfg["events"].get(ev_key, {})
        ev_on     = ev_cfg.get("enabled", True)
        sound_id  = ev_cfg.get("sound", "builtin:done")
        is_custom = not sound_id.startswith("builtin:")
        slabel    = Path(sound_id).name if is_custom else BUILTIN_MAP.get(sound_id, ("", sound_id))[1]

        # Name row
        ev_icon  = "●" if ev_on else "○"
        ev_iattr = curses.color_pair(CP_GREEN) if ev_on else (curses.color_pair(CP_RED) | curses.A_DIM)
        row_attr = curses.color_pair(CP_SEL) if sel else (curses.color_pair(CP_NORMAL) | curses.A_BOLD)

        if sel:
            put(y, 1, "▶", curses.color_pair(CP_ACCENT) | curses.A_BOLD)
        put(y, 3, f"{ev_icon}", ev_iattr if not sel else curses.color_pair(CP_SEL))
        put(y, 5, f"{ev_name:<22}", row_attr)
        put(y, 29, ev_desc, curses.color_pair(CP_DIM) | curses.A_DIM)

        # Sound row
        if sel:
            put(y + 1, 5, f"◄  {slabel}  ►",
                curses.color_pair(CP_ACCENT) | curses.A_BOLD)
            if is_custom:
                put(y + 1, 5 + 4 + len(slabel) + 4, "[custom file]",
                    curses.color_pair(CP_YELLOW) | curses.A_DIM)
        else:
            put(y + 1, 5, f"   {slabel}", curses.color_pair(CP_DIM) | curses.A_DIM)

        y += 3

    # ── Bottom bar ──
    bar_y = h - 2
    put(bar_y, 0, "─" * w, curses.color_pair(CP_TITLE) | curses.A_DIM)
    help_items = [
        ("W", "save"),
        ("Q", "quit"),
        ("T", "test"),
        ("F", "file picker"),
        ("S", "toggle event"),
    ]
    x = 2
    for k, v in help_items:
        put(bar_y + 1, x, k, curses.color_pair(CP_ACCENT) | curses.A_BOLD)
        put(bar_y + 1, x + 1, f" {v}", curses.color_pair(CP_DIM) | curses.A_DIM)
        x += len(k) + len(v) + 4

    # ── Status ──
    if status:
        put(h - 1, w - len(status) - 3, status,
            curses.color_pair(CP_GREEN) | curses.A_BOLD)

    # ── Unsaved indicator ──
    if not saved:
        put(0, w - 12, " unsaved ● ", curses.color_pair(CP_YELLOW) | curses.A_BOLD)

    stdscr.refresh()


# ── Main loop ─────────────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    init_colors()
    stdscr.keypad(True)
    stdscr.timeout(80)

    cfg        = load_config()
    cursor     = 0
    total_rows = 3 + len(EVENTS)
    status     = ""
    stimer     = 0
    saved      = True

    def set_status(msg, ticks=40):
        nonlocal status, stimer
        status, stimer = msg, ticks

    def mark_dirty():
        nonlocal saved
        saved = False

    while True:
        if stimer > 0:
            stimer -= 1
        elif stimer == 0:
            status = ""

        draw(stdscr, cfg, cursor, status, saved)
        key = stdscr.getch()
        if key == -1:
            continue

        # ── Navigation ──
        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)

        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(total_rows - 1, cursor + 1)

        # ── Quit / Save ──
        elif key in (ord("q"), ord("Q")):
            if not saved:
                try:
                    save_config(cfg)
                except Exception:
                    pass
            break

        elif key in (ord("w"), ord("W")):
            try:
                save_config(cfg)
                saved = True
                set_status("✓ saved", 50)
            except Exception as e:
                set_status(f"✗ {e}", 80)

        # ── Global toggle (row 0) ──
        elif cursor == 0 and key in (ord(" "), curses.KEY_ENTER, 10, 13):
            cfg["enabled"] = not cfg["enabled"]
            mark_dirty()
            set_status("sounds " + ("ON" if cfg["enabled"] else "OFF"))

        # ── Volume (row 1) ──
        elif cursor == 1:
            if key == curses.KEY_LEFT:
                cfg["volume"] = max(0.0, round(cfg["volume"] - 0.05, 2))
                mark_dirty(); set_status(f"volume {int(cfg['volume']*100)}%")
            elif key == curses.KEY_RIGHT:
                cfg["volume"] = min(1.0, round(cfg["volume"] + 0.05, 2))
                mark_dirty(); set_status(f"volume {int(cfg['volume']*100)}%")
            elif key in (ord("t"), ord("T")):
                ev_cfg = cfg["events"].get("Stop", {})
                play_sound(ev_cfg.get("sound", "builtin:done"), cfg["volume"])
                set_status("testing…")

        # ── Min duration (row 2) ──
        elif cursor == 2:
            if key == curses.KEY_LEFT:
                cfg["min_duration_secs"] = max(0, int(cfg.get("min_duration_secs", 60)) - 15)
                mark_dirty(); set_status(f"min duration {fmt_duration(cfg['min_duration_secs'])}")
            elif key == curses.KEY_RIGHT:
                cfg["min_duration_secs"] = min(600, int(cfg.get("min_duration_secs", 60)) + 15)
                mark_dirty(); set_status(f"min duration {fmt_duration(cfg['min_duration_secs'])}")

        # ── Event rows ──
        elif cursor >= 3:
            ei     = cursor - 3
            ev_key = EVENTS[ei][0]
            ev_cfg = cfg["events"].setdefault(ev_key, {"sound": "builtin:done", "enabled": True})
            sid    = ev_cfg.get("sound", "builtin:done")

            if key == curses.KEY_LEFT:
                base  = sid if sid in BUILTIN_IDS else BUILTIN_IDS[0]
                ev_cfg["sound"] = BUILTIN_IDS[(BUILTIN_IDS.index(base) - 1) % len(BUILTIN_IDS)]
                mark_dirty(); set_status(f"◄ {BUILTIN_MAP[ev_cfg['sound']][1]}")

            elif key == curses.KEY_RIGHT:
                base  = sid if sid in BUILTIN_IDS else BUILTIN_IDS[0]
                ev_cfg["sound"] = BUILTIN_IDS[(BUILTIN_IDS.index(base) + 1) % len(BUILTIN_IDS)]
                mark_dirty(); set_status(f"► {BUILTIN_MAP[ev_cfg['sound']][1]}")

            elif key in (ord("t"), ord("T"), curses.KEY_ENTER, 10, 13):
                play_sound(sid, cfg["volume"])
                lbl = Path(sid).name if not sid.startswith("builtin:") else BUILTIN_MAP[sid][1]
                set_status(f"♪ {lbl}")

            elif key in (ord("f"), ord("F")):
                curses.curs_set(1)
                pick = file_browser(stdscr)
                curses.curs_set(0)
                if pick:
                    ev_cfg["sound"] = pick
                    mark_dirty()
                    set_status(f"✓ {Path(pick).name}")

            elif key in (ord("s"), ord("S")):
                ev_cfg["enabled"] = not ev_cfg.get("enabled", True)
                mark_dirty()
                onoff = "on" if ev_cfg["enabled"] else "off"
                set_status(f"{EVENTS[ei][1]} {onoff}")


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print(f"Config: {CONFIG_PATH}")