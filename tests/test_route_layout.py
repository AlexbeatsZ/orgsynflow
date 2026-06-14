from pathlib import Path

from core.route import load_demo_routes
from core.route_layout import layout_route


def test_layout_route_returns_nodes_and_edges_for_visualization() -> None:
    route = load_demo_routes(Path("data/demo_routes/aspirin.json"))[0]

    graph = layout_route(route)

    assert len(graph.nodes) == len(route.molecules)
    assert graph.edges
    assert graph.nodes[route.target_id].x > 0
