from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.aizynth_adapter import predict_routes_with_fallback
from core.molecule import has_rdkit, molecule_svg, summarize_molecule
from core.reaction_explain import explain_reaction
from core.report import render_report
from core.route import Route, load_demo_routes, route_to_dot
from core.scoring import score_route


DEMO_DIR = ROOT / "data" / "demo_routes"
DEMO_TARGETS = {
    "Aspirin": {
        "smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "path": DEMO_DIR / "aspirin.json",
    },
    "Paracetamol": {
        "smiles": "CC(=O)Nc1ccc(O)cc1",
        "path": DEMO_DIR / "paracetamol.json",
    },
}


def main() -> None:
    st.set_page_config(page_title="OrgSyn Flow 有机合成工作台", layout="wide")
    st.title("OrgSyn Flow 有机合成工作台")
    st.caption("V0-V2：目标分子输入、路线展示、描述符表、报告导出、AiZynthFinder 回退接口与反应中心解释。")

    with st.sidebar:
        st.header("输入")
        selected_target = st.selectbox("演示目标", list(DEMO_TARGETS))
        default_smiles = DEMO_TARGETS[selected_target]["smiles"]
        smiles = st.text_input("目标分子 SMILES", value=default_smiles)
        engine = st.radio(
            "路线来源",
            ["演示 JSON", "AiZynthFinder + 演示回退"],
            horizontal=False,
        )
        max_routes = st.slider("最多路线数", min_value=1, max_value=5, value=3)
        st.divider()
        st.write("RDKit：", "可用" if has_rdkit() else "未安装")

    fallback_routes = load_demo_routes(DEMO_TARGETS[selected_target]["path"])
    if engine == "AiZynthFinder + 演示回退":
        result = predict_routes_with_fallback(smiles, fallback_routes, max_routes=max_routes)
        routes = result.routes
        status = result.status
    else:
        routes = fallback_routes[:max_routes]
        status = "已加载内置演示路线。"

    target = summarize_molecule(smiles)
    scores = {route.id: score_route(route) for route in routes}

    render_status(status)
    render_target_section(target)
    render_route_comparison(routes, scores)
    render_routes(routes, scores)
    render_report_download(target, routes, scores, status)


def render_status(status: str) -> None:
    if "fallback" in status.lower() or "not found" in status.lower() or "using bundled" in status.lower():
        st.warning(status)
    else:
        st.success(status)


def render_target_section(target) -> None:
    st.subheader("目标分子")
    left, right = st.columns([1, 2])
    with left:
        svg = molecule_svg(target.smiles)
        if svg:
            st.image(svg, use_container_width=True)
        else:
            st.info("执行 `uv sync --extra chem` 安装 RDKit 后可显示分子结构图。")
    with right:
        st.dataframe(
            pd.DataFrame([target.as_display_dict()]).T.rename(columns={0: "Value"}),
            use_container_width=True,
        )
        if target.warning:
            st.warning(target.warning)


def render_route_comparison(routes: list[Route], scores) -> None:
    st.subheader("路线对比")
    rows = []
    for route in routes:
        score = scores[route.id]
        rows.append(
            {
                "路线": route.title,
                "来源": route.source,
                "综合分": score.route_score,
                "步数": route.depth,
                "叶子前体": route.precursor_count,
                "可购买": route.stock_count,
                "模型": score.model_score,
                "原料": score.stock_score,
                "步数分": score.step_score,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_routes(routes: list[Route], scores) -> None:
    st.subheader("路线树")
    for route in sorted(routes, key=lambda item: scores[item.id].route_score, reverse=True):
        with st.expander(f"{route.title} · 综合分 {scores[route.id].route_score}", expanded=True):
            st.graphviz_chart(route_to_dot(route), use_container_width=True)
            st.caption(scores[route.id].explanation)
            render_route_molecules(route)
            render_route_steps(route)


def render_route_molecules(route: Route) -> None:
    st.markdown("**分子清单**")
    columns = st.columns(3)
    for index, molecule in enumerate(route.molecules):
        with columns[index % 3]:
            st.markdown(f"**{molecule.name}**")
            svg = molecule_svg(molecule.smiles, size=(260, 180))
            if svg:
                st.image(svg, use_container_width=True)
            st.code(molecule.smiles, language="text")
            st.caption("可购买" if molecule.in_stock else "目标/中间体")


def render_route_steps(route: Route) -> None:
    st.markdown("**反应步骤与解释**")
    molecules = route.molecule_by_id
    rows = []
    for step in route.steps:
        explanation = explain_reaction(step.reaction_smiles, step.template)
        rows.append(
            {
                "步骤": step.id,
                "产物": molecules[step.product_id].name,
                "前体": " + ".join(molecules[item].name for item in step.precursor_ids),
                "反应类型": explanation.reaction_type,
                "形成键": "、".join(explanation.formed_bonds) or "-",
                "断裂键": "、".join(explanation.broken_bonds) or "-",
                "反应中心": "、".join(explanation.reaction_center) or "-",
                "解释": explanation.summary,
                "策略分": step.policy_score if step.policy_score is not None else "-",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_report_download(target, routes: list[Route], scores, status: str) -> None:
    st.subheader("报告导出")
    report = render_report(target, routes, scores, status)
    st.download_button(
        "下载 Markdown 报告",
        data=report,
        file_name="orgsynflow_route_report.md",
        mime="text/markdown",
    )
    with st.expander("预览报告"):
        st.markdown(report)


if __name__ == "__main__":
    main()
