from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.molecule import MoleculeSummary
from core.reaction_explain import explain_reaction
from core.route import Route
from core.scoring import RouteScore


def render_report(
    target: MoleculeSummary,
    routes: list[Route],
    scores: dict[str, RouteScore],
    status: str,
) -> str:
    template_dir = Path(__file__).resolve().parents[1] / "reports" / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(disabled_extensions=("md",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("route_report.md.j2")
    return template.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        target=target,
        routes=routes,
        scores=scores,
        status=status,
        explain_reaction=explain_reaction,
    )
