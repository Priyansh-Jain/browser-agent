"""A tiny directed-acyclic-graph of skill invocations.

The Planner emits a plan as plain JSON ``{"nodes": [...], "edges": [...]}``.
The orchestrator turns it into a ``DAG`` and executes nodes in topological
order. Each node names a skill from the catalogue plus the params to call it
with. This module is generic -- it has no idea what "browser" or "huggingface"
means.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Node:
    id: str
    skill: str
    title: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    deps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "skill": self.skill,
            "title": self.title or self.id,
            "params": self.params,
            "deps": self.deps,
        }


class DAG:
    def __init__(self, nodes: List[Node]):
        self.nodes: Dict[str, Node] = {n.id: n for n in nodes}
        self._validate()

    @classmethod
    def from_dict(cls, plan: Dict[str, Any]) -> "DAG":
        raw_nodes = plan.get("nodes", [])
        # Edges can be given explicitly as [from, to] pairs, or implied by each
        # node's "deps". We support both and merge them.
        edge_deps: Dict[str, List[str]] = {}
        for edge in plan.get("edges", []):
            if isinstance(edge, (list, tuple)) and len(edge) == 2:
                src, dst = edge
                edge_deps.setdefault(dst, []).append(src)
            elif isinstance(edge, dict):
                edge_deps.setdefault(edge["to"], []).append(edge["from"])
        nodes = []
        for n in raw_nodes:
            nid = n["id"]
            deps = list(n.get("deps", [])) + edge_deps.get(nid, [])
            nodes.append(
                Node(
                    id=nid,
                    skill=n["skill"],
                    title=n.get("title", ""),
                    params=n.get("params", {}),
                    deps=sorted(set(deps)),
                )
            )
        return cls(nodes)

    def _validate(self) -> None:
        for n in self.nodes.values():
            for d in n.deps:
                if d not in self.nodes:
                    raise ValueError(f"Node {n.id!r} depends on unknown node {d!r}")
        # cycle check happens implicitly in topo_order()
        self.topo_order()

    def topo_order(self) -> List[Node]:
        """Kahn's algorithm -> deterministic topological order."""
        indeg = {nid: 0 for nid in self.nodes}
        for n in self.nodes.values():
            for _ in n.deps:
                indeg[n.id] += 1
        # ready = nodes with no unmet deps, sorted for determinism
        ready = sorted([nid for nid, d in indeg.items() if d == 0])
        order: List[Node] = []
        while ready:
            nid = ready.pop(0)
            order.append(self.nodes[nid])
            for m in self.nodes.values():
                if nid in m.deps:
                    indeg[m.id] -= 1
                    if indeg[m.id] == 0:
                        ready.append(m.id)
            ready.sort()
        if len(order) != len(self.nodes):
            raise ValueError("Plan DAG contains a cycle")
        return order

    def to_dict(self) -> Dict[str, Any]:
        edges = []
        for n in self.nodes.values():
            for d in n.deps:
                edges.append([d, n.id])
        return {"nodes": [n.to_dict() for n in self.nodes.values()], "edges": edges}

    def to_mermaid(self) -> str:
        """Render the plan as a Mermaid flowchart (GitHub renders this natively)."""
        lines = ["flowchart TD"]
        for n in self.nodes.values():
            label = (n.title or n.id).replace('"', "'")
            lines.append(f'    {n.id}["{label}<br/><i>{n.skill}</i>"]')
        for n in self.nodes.values():
            for d in n.deps:
                lines.append(f"    {d} --> {n.id}")
        return "\n".join(lines)
