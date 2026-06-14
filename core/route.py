from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RouteMolecule:
    id: str
    name: str
    smiles: str
    in_stock: bool = False


@dataclass(frozen=True)
class RouteStep:
    id: str
    product_id: str
    precursor_ids: list[str]
    reaction_smiles: str | None = None
    policy_score: float | None = None
    template: str | None = None


@dataclass(frozen=True)
class Route:
    id: str
    title: str
    target_id: str
    molecules: list[RouteMolecule]
    steps: list[RouteStep]
    source: str = "demo"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def molecule_by_id(self) -> dict[str, RouteMolecule]:
        return {molecule.id: molecule for molecule in self.molecules}

    @property
    def depth(self) -> int:
        return len(self.steps)

    @property
    def stock_count(self) -> int:
        return sum(1 for molecule in self.leaf_precursors if molecule.in_stock)

    @property
    def precursor_count(self) -> int:
        return len(self.leaf_precursors)

    @property
    def leaf_precursors(self) -> list[RouteMolecule]:
        product_ids = {step.product_id for step in self.steps}
        return [molecule for molecule in self.molecules if molecule.id not in product_ids]

    @property
    def mean_policy_score(self) -> float | None:
        scores = [step.policy_score for step in self.steps if step.policy_score is not None]
        return sum(scores) / len(scores) if scores else None


def load_demo_routes(path: Path) -> list[Route]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [route_from_dict(item, source="demo") for item in payload["routes"]]


def route_from_dict(payload: dict[str, Any], source: str = "demo") -> Route:
    return Route(
        id=payload["id"],
        title=payload.get("title", payload["id"]),
        target_id=payload["target_id"],
        molecules=[RouteMolecule(**item) for item in payload["molecules"]],
        steps=[RouteStep(**item) for item in payload["steps"]],
        source=source,
        metadata=payload.get("metadata", {}),
    )


def route_to_dot(route: Route) -> str:
    molecules = route.molecule_by_id
    lines = [
        "digraph route {",
        "rankdir=RL;",
        'node [shape=box, style="rounded,filled", fontname="Arial"];',
        'edge [fontname="Arial"];',
    ]
    for molecule in route.molecules:
        fill = "#d7f5df" if molecule.in_stock else "#e8f1ff"
        label = f"{molecule.name}\\n{molecule.smiles}"
        lines.append(f'"{molecule.id}" [label="{_dot_escape(label)}", fillcolor="{fill}"];')

    for step in route.steps:
        product = molecules[step.product_id]
        for precursor_id in step.precursor_ids:
            precursor = molecules[precursor_id]
            label = step.template or step.id
            lines.append(
                f'"{precursor.id}" -> "{product.id}" [label="{_dot_escape(label)}"];'
            )

    lines.append("}")
    return "\n".join(lines)


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
