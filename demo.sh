#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# ONE-COMMAND DEMO  —  run this, then record your screen.
#
#   ./demo.sh
#
# Opens a VISIBLE Chromium window and drives Hugging Face live (filter → sort →
# scroll → open 3 model pages), then opens the Replay Viewer showing all 8
# required elements.
#
# • If ANTHROPIC_API_KEY is set      -> every LLM call is fully live.
# • If not                           -> an offline DEMO gateway mocks the LLM so
#                                        the plan, vision read, and cost summary
#                                        are still fully populated for recording.
# ────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

GOAL="${1:-Compare the top 3 Hugging Face text-generation models, ranked by likes}"

echo "🎬  Starting visible browser demo — get your screen recorder ready..."
sleep 1

HEADLESS=0 SLOW_MO=600 DEMO_MODE=1 FORCE_VISION_DEMO=1 "$PY" run.py "$GOAL"

# Open the interactive replay viewer for the recording (macOS / Linux best-effort)
REPLAY="artifacts/latest/replay.html"
echo ""
echo "📂  Opening replay viewer: $REPLAY"
open "$REPLAY" 2>/dev/null || xdg-open "$REPLAY" 2>/dev/null || \
  echo "   (open $REPLAY manually in your browser)"
