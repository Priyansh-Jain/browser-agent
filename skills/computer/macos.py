"""Native-macOS control backend (no third-party deps -- pure ``osascript``).

Provides the L1 / L2a / L2b primitives for native apps:

  * L1  -- ``launch`` / ``activate`` / ``quit`` / ``menu`` (deterministic verbs)
  * L2a -- ``key_code`` / ``keystroke`` / ``type_sequence`` / ``hotkey`` (keyboard)
  * L2b -- ``ax_static_texts`` / ``ax_value`` (read the accessibility tree, text only)
            and ``clipboard_copy`` (Cmd-C) + ``pbpaste`` for a deterministic read

Synthetic keystrokes and AX reads both require the host process to hold macOS
**Accessibility** permission; ``accessibility_ok`` preflights that so a missing
grant degrades to a clean L4 "blocked" rather than a crash.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

# macOS virtual key codes we use
KEY_RETURN = 36
KEY_ESCAPE = 53


class PermissionDenied(PermissionError):
    """Raised when System Events is refused assistive access (error -1719)."""


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _osa(script: str, timeout: int = 20) -> str:
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    out, err = p.stdout.strip(), p.stderr.strip()
    if p.returncode != 0:
        low = err.lower()
        if ("-1719" in err or "(1002)" in err or "not allowed assistive access" in low
                or "not allowed to send keystrokes" in low or "assistive" in low):
            raise PermissionDenied(err or "Accessibility permission required")
        raise RuntimeError(err or f"osascript exit {p.returncode}")
    return out


class MacOSBackend:
    def __init__(self, trace=None):
        self.trace = trace

    # ---------------------------------------------------------------- preflight
    def accessibility_ok(self) -> bool:
        """True only if we can actually read another process's UI elements -- the
        same Accessibility grant that gates synthetic keystrokes. (Enumerating
        process *names* is allowed without it, so that is NOT a valid probe.)"""
        for proc in ("Finder", "Dock"):
            try:
                _osa(f'tell application "System Events" to tell process "{proc}" to return (count of windows)')
                return True
            except PermissionDenied:
                return False
            except Exception:
                continue
        return False

    # ---------------------------------------------------------------- L1: verbs
    def launch(self, app: str) -> None:
        subprocess.run(["open", "-a", app], check=False, capture_output=True)
        time.sleep(1.3)
        self.activate(app)

    def activate(self, app: str) -> None:
        _osa(f'tell application "{app}" to activate')
        time.sleep(0.5)

    def quit(self, app: str) -> None:
        try:
            _osa(f'tell application "{app}" to quit')
        except Exception:
            pass

    def is_running(self, app: str) -> bool:
        try:
            return _osa(f'tell application "System Events" to return (exists process "{app}")') == "true"
        except Exception:
            return False

    def menu(self, process: str, menu: str, item: str) -> bool:
        _osa(f'tell application "System Events" to tell process "{process}" '
             f'to click menu item "{_esc(item)}" of menu 1 of menu bar item "{_esc(menu)}" of menu bar 1')
        time.sleep(0.35)
        return True

    # ------------------------------------------------------------ L2a: keyboard
    def key_code(self, code: int, using: Optional[str] = None) -> None:
        u = f" using {using}" if using else ""
        _osa(f'tell application "System Events" to key code {code}{u}')
        time.sleep(0.12)

    def keystroke(self, keys: str, using: Optional[str] = None) -> None:
        u = f" using {using}" if using else ""
        _osa(f'tell application "System Events" to keystroke "{_esc(keys)}"{u}')
        time.sleep(0.12)

    def hotkey(self, key: str, *mods: str) -> None:
        """e.g. hotkey('c', 'command') -> Cmd-C; hotkey('n','command','shift')."""
        using = " & ".join(f"{m} down" for m in mods) if mods else None
        self.keystroke(key, using=("{" + using + "}") if using else None)

    def type_sequence(self, text: str, per_delay: float = 0.06) -> None:
        """Type one character at a time -- robust for immediate-execution apps
        (e.g. Calculator) that can drop a fast multi-char keystroke."""
        for ch in text:
            self.keystroke(ch)
            time.sleep(per_delay)

    # --------------------------------------------------------- L2b: read the AX
    def ax_static_texts(self, process: str) -> List[str]:
        """Every static-text value reachable from the front window (one group deep)."""
        vals: List[str] = []
        for ref in (
            "value of every static text of window 1",
            "value of every static text of (every group of window 1)",
            "value of every static text of (every group of (every group of window 1))",
        ):
            try:
                out = _osa(f'tell application "System Events" to tell process "{process}" to return {ref}')
            except PermissionDenied:
                raise
            except Exception:
                continue
            for piece in out.split(","):
                piece = piece.strip()
                if piece and piece not in vals and piece != "missing value":
                    vals.append(piece)
        return vals

    def ax_value(self, process: str, ref: str) -> Optional[str]:
        try:
            v = _osa(f'tell application "System Events" to tell process "{process}" to return {ref}')
            return v or None
        except PermissionDenied:
            raise
        except Exception:
            return None

    # ----------------------------------------------------- L2b: clipboard read
    def clipboard_copy(self) -> None:
        self.hotkey("c", "command")
        time.sleep(0.25)

    @staticmethod
    def pbpaste() -> str:
        try:
            return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def pbcopy(text: str) -> None:
        try:
            subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
        except Exception:
            pass

    # ------------------------------------------------------------- screenshots
    def window_region(self, process: str) -> Optional[Tuple[int, int, int, int]]:
        try:
            pos = _osa(f'tell application "System Events" to tell process "{process}" to return position of window 1')
            siz = _osa(f'tell application "System Events" to tell process "{process}" to return size of window 1')
            x, y = (int(float(n)) for n in pos.split(","))
            w, h = (int(float(n)) for n in siz.split(","))
            if w > 0 and h > 0:
                return x, y, w, h
        except Exception:
            return None
        return None

    def screenshot(self, out_path: str, process: Optional[str] = None) -> bool:
        """Capture the app window region if we can read its AX bounds, else the
        full screen. Returns True only if a non-trivial PNG was written. (Capturing
        *another app's* window pixels needs Screen-Recording permission on modern
        macOS; without it this still writes a frame, just of the desktop.)"""
        args = ["screencapture", "-x", "-o"]
        region = self.window_region(process) if process else None
        if region:
            x, y, w, h = region
            args.append(f"-R{x},{y},{w},{h}")
        args.append(out_path)
        try:
            subprocess.run(args, capture_output=True, text=True, timeout=12)
        except Exception:
            return False
        p = Path(out_path)
        return p.exists() and p.stat().st_size > 800
