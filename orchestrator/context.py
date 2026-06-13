"""Shared run context (the "blackboard").

Skills communicate by reading/writing well-known keys on ``ctx.bb`` rather than
by the orchestrator wiring outputs to inputs. This keeps the orchestrator
generic: it just runs nodes in order; data flows through the blackboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class Context:
    goal: str
    config: Any                 # config.Config
    gateway: Any                # gateway.llm_gateway.LLMGateway
    artifacts_dir: Path
    run_id: str
    bb: Dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        self.bb[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.bb.get(key, default)
