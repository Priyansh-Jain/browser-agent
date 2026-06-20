#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# ONE-COMMAND COMPUTER-USE DEMO  —  run this, then record your screen.
#
#   ./demo_cu.sh
#
# Drives three real desktop tasks through the five-layer control cascade:
#   1. Calculator  — deterministic hotkeys (L2a), verified with ZERO vision
#   2. Canvas game — a no-ARIA <canvas>, value read by VISION (forces L3)
#   3. Cursor      — Electron over electron_debugging_port (the page path)
#
# • ANTHROPIC_API_KEY set  -> vision read + text-judge are fully live.
# • not set                -> the offline MOCK gateway stands in (same as the
#                             browser demo), so every layer is still exercised.
#
# Requirements: macOS Accessibility permission for the terminal/host app
# (System Settings → Privacy & Security → Accessibility) so synthetic keystrokes
# and AX reads are allowed. Cursor must be installed for task 3.
# ────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "🎬  Computer-Use demo — Calculator, then a canvas game, then Cursor."
echo "    (the canvas window is visible; Calculator & Cursor are real GUI apps)"
sleep 1

HEADLESS=0 SLOW_MO=250 "$PY" run_cu.py "$@"

REPLAY="artifacts/cu-latest/replay.html"
echo ""
echo "📂  Opening replay viewer: $REPLAY"
open "$REPLAY" 2>/dev/null || xdg-open "$REPLAY" 2>/dev/null || \
  echo "   (open $REPLAY manually in your browser)"
echo "🗂   Trajectory evidence: artifacts/cu-latest/trajectory/<task>/"
