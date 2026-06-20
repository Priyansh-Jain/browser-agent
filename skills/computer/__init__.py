"""Computer-use skill package.

The desktop-control analogue of ``skills/browser/``. It drives *native macOS
apps* (Calculator), *Electron apps over the remote debugging port* (Cursor), and
*canvas/game targets with no accessibility* (a local browser game) through the
same "cheapest correct path?" discipline the Browser skill uses -- only here the
ladder is the **five-layer control cascade** (see ``layers.py``):

    L1 deterministic  ->  page (Electron CDP)  ->  L2a hotkeys  ->
    L2b a11y/text-LLM  ->  L3 vision  ->  L4 blocked

Nothing in here edits the (frozen) orchestrator. Everything plugs into the
catalogue as Skills, exactly like the Browser skill.
"""
from __future__ import annotations

from .cascade import Cascade
from .recorder import Recorder

__all__ = ["Cascade", "Recorder"]
