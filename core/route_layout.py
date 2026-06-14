from __future__ import annotations

from dataclasses import dataclass

from core.route import Route


@dataclass(frozen=True)
class LayoutNode:
    id: str
    label: str
    x: int
    y: int
    in_stock: bool


@dataclass(frozen=True)
class LayoutEdge:
    source_id: str
    target_id: str
    label: str


@dataclass(frozen=True)
class RouteGraphLayout:
    nodes: dict[str, LayoutNode]
    edges: list[LayoutEdge]


def layout_route(route: Route, x_gap: int = 260, y_gap: int = 110) -> RouteGraphLayout:
    children_by_product: dict[str, list[str]] = {
        step.product_id: step.precursor_ids for step in route.steps
    }
    depth_by_id: dict[str, int] = {}

    def assign_depth(molecule_id: str, depth: int) -> None:
        depth_by_id[molecule_id] = max(depth_by_id.get(molecule_id, 0), depth)
        for child_id in children_by_product.get(molecule_id, []):
            assign_depth(child_id, depth + 1)

    assign_depth(route.target_id, 0)
    for molecule in route.molecules:
        depth_by_id.setdefault(molecule.id, 0)

    grouped: dict[int, list[str]] = {}
    for molecule_id, depth in depth_by_id.items():
        grouped.setdefault(depth, []).append(molecule_id)

    molecules = route.molecule_by_id
    nodes: dict[str, LayoutNode] = {}
    max_depth = max(grouped) if grouped else 0
    for depth, molecule_ids in grouped.items():
        molecule_ids.sort()
        for index, molecule_id in enumerate(molecule_ids):
            molecule = molecules[molecule_id]
            nodes[molecule_id] = LayoutNode(
                id=molecule_id,
                label=f"{molecule.name}\n{molecule.smiles}",
                x=40 + (max_depth - depth) * x_gap,
                y=40 + index * y_gap,
                in_stock=molecule.in_stock,
            )

    edges: list[LayoutEdge] = []
    for step in route.steps:
        for precursor_id in step.precursor_ids:
            edges.append(
                LayoutEdge(
                    source_id=precursor_id,
                    target_id=step.product_id,
                    label=step.template or step.id,
                )
            )
    return RouteGraphLayout(nodes=nodes, edges=edges)
