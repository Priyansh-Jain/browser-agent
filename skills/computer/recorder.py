"""Trajectory recorder -- ``start_recording`` / ``stop_recording``.

Every computer-use run is recorded as a **trajectory directory**, which is the
artefact submitted as evidence:

    artifacts/cu-run-<ts>/trajectory/<task_id>/
        frames/0001_<caption>.png   # one ordered frame per observable step
        frames/0002_<caption>.png
        ...
        trajectory.jsonl            # one JSON line per frame / action / decision
        meta.json                   # task, status, layers_used, verification verdict

Frames are captured by a backend-supplied ``screenshot_fn`` (Playwright's own
rasteriser for Electron/canvas targets -- needs no Screen-Recording permission;
``screencapture`` for native windows). Observations are mirrored into the shared
``Trace`` so the unified ``trace.json`` / ``replay.html`` stay the single source
of truth, while the per-task trajectory directory is self-contained.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _slug(s: str, n: int = 36) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return (s or "frame")[:n]


class Recorder:
    def __init__(
        self,
        trace,
        traj_root: Path,
        task_id: str,
        screenshot_fn: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.trace = trace
        self.task_id = task_id
        self.dir = Path(traj_root) / task_id
        self.frames_dir = self.dir / "frames"
        self.screenshot_fn = screenshot_fn
        self._n = 0
        self._jsonl = None
        self.started: Optional[float] = None
        self.layers_used: List[str] = []
        self.frames: List[Dict[str, Any]] = []

    # ---- lifecycle ----
    def start_recording(self, title: str = "") -> "Recorder":
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl = open(self.dir / "trajectory.jsonl", "w")
        self.started = time.time()
        self._write({"kind": "start", "task": self.task_id, "title": title, "t": 0.0})
        self.trace.log(f"start_recording[{self.task_id}] -> {self.dir}", "info")
        return self

    def stop_recording(self, status: str = "ok", verdict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        meta = {
            "task": self.task_id,
            "status": status,
            "duration_sec": self._t(),
            "frames": self._n,
            "layers_used": self.layers_used,
            "verdict": verdict or {},
        }
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        self._write({"kind": "stop", "status": status, "t": self._t(), "verdict": verdict or {}})
        if self._jsonl:
            self._jsonl.close()
            self._jsonl = None
        self.trace.log(f"stop_recording[{self.task_id}] status={status} frames={self._n}", "info")
        return meta

    # ---- recording ----
    def frame(self, caption: str, capture: bool = True, also_trace: bool = True) -> str:
        self._n += 1
        name = f"{self._n:04d}_{_slug(caption)}.png"
        rel = f"{self.task_id}/frames/{name}"
        captured = False
        if capture and self.screenshot_fn:
            try:
                captured = bool(self.screenshot_fn(str(self.frames_dir / name)))
            except Exception as e:  # noqa: BLE001
                self.trace.log(f"frame capture failed ({caption}): {e!r}", "warn")
        self.frames.append({"i": self._n, "caption": caption, "frame": rel, "captured": captured, "t": self._t()})
        self._write({"kind": "frame", "i": self._n, "caption": caption,
                     "frame": rel, "captured": captured, "t": self._t()})
        if also_trace and captured:
            self.trace.record_screenshot(f"trajectory/{rel}", caption)
        return rel

    def attach_frame(self, caption: str, image_path: str, also_trace: bool = True) -> str:
        """Record an already-rendered image (e.g. a set-of-marks overlay) as the
        next ordered frame in the trajectory."""
        self._n += 1
        name = f"{self._n:04d}_{_slug(caption)}.png"
        rel = f"{self.task_id}/frames/{name}"
        captured = False
        try:
            shutil.copyfile(image_path, self.frames_dir / name)
            captured = True
        except Exception as e:  # noqa: BLE001
            self.trace.log(f"attach_frame failed ({caption}): {e!r}", "warn")
        self.frames.append({"i": self._n, "caption": caption, "frame": rel, "captured": captured, "t": self._t()})
        self._write({"kind": "frame", "i": self._n, "caption": caption,
                     "frame": rel, "captured": captured, "t": self._t()})
        if also_trace and captured:
            self.trace.record_screenshot(f"trajectory/{rel}", caption)
        return rel

    def event(self, kind: str, **data: Any) -> None:
        if kind == "cascade":
            chosen = data.get("chosen")
            if chosen and chosen not in self.layers_used:
                self.layers_used.append(chosen)
        self._write({"kind": kind, "t": self._t(), **data})

    # ---- internals ----
    def _write(self, rec: Dict[str, Any]) -> None:
        if self._jsonl:
            self._jsonl.write(json.dumps(rec, default=str) + "\n")
            self._jsonl.flush()

    def _t(self) -> float:
        return round(time.time() - (self.started or time.time()), 3)
