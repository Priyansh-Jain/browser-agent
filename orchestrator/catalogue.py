"""The Skill Catalogue.

Every capability the agent has is a Skill registered here. The Planner is given
the catalogue's manifest (names + descriptions) so it can compose a plan from
exactly the skills that exist. To add behaviour you register a new skill or
extend an existing one -- you do not touch the orchestrator.
"""
from __future__ import annotations

from typing import Dict, List

from .skill import Skill


class SkillCatalogue:
    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> "SkillCatalogue":
        if not skill.name:
            raise ValueError("Skill must define a non-empty name")
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill
        return self

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(
                f"Skill {name!r} not in catalogue. Known: {sorted(self._skills)}"
            )
        return self._skills[name]

    def has(self, name: str) -> bool:
        return name in self._skills

    def names(self) -> List[str]:
        return sorted(self._skills)

    def manifest(self) -> List[dict]:
        return [self._skills[n].manifest() for n in self.names()]
