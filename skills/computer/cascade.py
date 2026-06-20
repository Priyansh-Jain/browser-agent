"""The cheapest-correct-path cascade for computer use.

``Cascade.run(intent, rungs, ...)`` takes an *ordered* list of ``(layer, fn)``
rungs (cheapest first) and calls them in turn until one returns a value that
passes ``validate``. It records the full attempt ladder into the Trace as a
``path_decision`` -- including the rungs it never had to reach, so the replay
shows *why* (e.g.) vision was unnecessary. This is the direct analogue of the
Browser skill's ``PathSelector.extract``.

The same method serves both *interactions* (``kind="do"`` -- the fn performs an
action and returns truthy on success) and *reads/verifications* (``kind="read"``
-- the fn returns the observed value), because both follow identical discipline:
try cheap, stop at first success, record the ladder.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from .layers import BLOCKED, LAYER_COST

Rung = Tuple[str, Optional[Callable[[], Any]]]


def _describe(v: Any) -> str:
    if v is True:
        return "ok"
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return "dict{" + ",".join(list(v.keys())[:6]) + "}"
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."


class Cascade:
    def __init__(self, trace, recorder=None):
        self.trace = trace
        self.recorder = recorder

    def run(
        self,
        intent: str,
        rungs: List[Rung],
        *,
        validate: Optional[Callable[[Any], bool]] = None,
        primary: bool = True,
        kind: str = "read",
        target: str = "",
    ) -> Tuple[str, Any]:
        validate = validate or (lambda v: v not in (None, "", [], {}, False))
        attempts: List[dict] = []
        for idx, (layer, fn) in enumerate(rungs):
            if fn is None:
                attempts.append({"path": layer, "layer": layer, "ok": False, "note": "not applicable here"})
                continue
            try:
                val = fn()
                ok = bool(validate(val))
                attempts.append(
                    {"path": layer, "layer": layer, "ok": ok,
                     "note": _describe(val) if ok else "empty / invalid"}
                )
                if ok:
                    # Note the cheaper-than-this-would-have-been rungs we never reached,
                    # so the replay shows the discipline (e.g. "vision: not reached").
                    for rest_layer, _ in rungs[idx + 1:]:
                        attempts.append(
                            {"path": rest_layer, "layer": rest_layer, "ok": None,
                             "note": "not reached (cheaper layer sufficed)"}
                        )
                    self._record(intent, attempts, layer, primary, kind, target, val)
                    return layer, val
            except PermissionError as e:
                attempts.append({"path": layer, "layer": layer, "ok": False,
                                 "note": f"permission denied: {e}"[:120]})
            except Exception as e:  # noqa: BLE001 - record and try the next rung
                attempts.append({"path": layer, "layer": layer, "ok": False,
                                 "note": f"{type(e).__name__}: {e}"[:120]})
        self._record(intent, attempts, BLOCKED, primary, kind, target, None)
        return BLOCKED, None

    # ---- a standalone capability check (records a decision without escalation) ----
    def note(self, intent: str, layer: str, ok: bool, detail: str, *, primary: bool = False) -> None:
        self.trace.record_path_decision(
            intent, [{"path": layer, "layer": layer, "ok": ok, "note": detail}],
            layer if ok else "failed", primary,
        )
        if self.recorder:
            self.recorder.event("check", intent=intent, layer=layer, ok=ok, note=detail)

    # ---- internals ----
    def _record(self, intent, attempts, chosen, primary, kind, target, val) -> None:
        self.trace.record_path_decision(intent, attempts, chosen, primary)
        self.trace.record_action(kind, target=intent, value=(target or _describe(val)), path=chosen)
        if self.recorder:
            self.recorder.event(
                "cascade", intent=intent, op=kind, chosen=chosen,
                ladder=[{"layer": a["layer"], "ok": a["ok"], "note": a["note"]} for a in attempts],
            )

    @staticmethod
    def cheapest_cost(decisions: List[dict]) -> int:
        return max((LAYER_COST.get(d.get("chosen"), 0) for d in decisions), default=0)
