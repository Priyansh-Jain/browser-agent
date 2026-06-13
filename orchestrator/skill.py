"""Skill interface.

A Skill is the ONLY unit of behaviour the orchestrator knows how to run. The
orchestrator never contains task-specific or site-specific logic; all of that
lives inside skills that are registered in the catalogue. New capabilities are
added by writing a new Skill (or extending an existing one such as the Browser
skill) -- never by editing the orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict


class Skill:
    """Base class for every catalogue skill.

    Subclasses set ``name`` / ``description`` and implement ``run``.
    ``description`` is shown to the Planner so it can compose a plan purely from
    the catalogue, without the orchestrator hard-coding any pipeline.
    """

    name: str = ""
    description: str = ""
    # Optional machine-readable hint of what the skill reads/writes on the
    # shared blackboard. Purely informational (used by the Planner + report).
    reads: tuple = ()
    writes: tuple = ()

    def run(self, ctx: "Context", trace: "Trace", **params: Any) -> Dict[str, Any]:  # noqa: F821
        raise NotImplementedError(f"Skill {self.name!r} does not implement run()")

    def manifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "reads": list(self.reads),
            "writes": list(self.writes),
        }
