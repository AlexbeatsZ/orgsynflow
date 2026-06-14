from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.molecule import molecule_svg
from services.workbench import (
    analyze_profile_from_logs,
    analyze_target,
    calculate_molecule_descriptors,
    calculate_reaction_features,
    estimate_single_reaction_yield,
    gaussian_status,
    list_adapters,
    make_gaussian_input,
    map_single_reaction,
    parse_gaussian_text,
    plan_single_transition_state,
    predict_molecule_properties,
    explain_single_reaction,
    summarize_target_molecule,
)


DEMO_TARGETS = {
    "Aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "Paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "Ethanol": "CCO",
}

SAMPLE_REACTION = "CCO>>CC=O"
SAMPLE_REACTANT_LOG = """
 SCF Done:  E(RB3LYP) =  -100.000000     A.U. after   10 cycles
 Frequencies --  100.00   200.00   300.00
 Sum of electronic and thermal Free Energies=        -100.000000
 Normal termination of Gaussian 16
""".strip()
SAMPLE_PRODUCT_LOG = """
 SCF Done:  E(RB3LYP) =  -100.020000     A.U. after   10 cycles
 Frequencies --  100.00   200.00   300.00
 Sum of electronic and thermal Free Energies=        -100.020000
 Normal termination of Gaussian 16
""".strip()
SAMPLE_TS_LOG = """
 SCF Done:  E(RB3LYP) =  -99.970000     A.U. after   10 cycles
 Frequencies --  -521.40   120.00   340.50
 Sum of electronic and thermal Free Energies=        -99.970000
 Normal termination of Gaussian 16
""".strip()


def main() -> None:
    st.set_page_config(page_title="OrgSynFlow", layout="wide")
    st.title("OrgSynFlow 有机合成与计算化学工作台")
    st.caption("路线预测、物性预测、反应解释、Gaussian 输入、过渡态计划与动力学估算。")

    adapters = list_adapters()
    _render_top_metrics(adapters)

    tabs = st.tabs(["分子与物性", "合成路线", "反应分析", "Gaussian / TS", "动力学", "适配器"])
    with tabs[0]:
        render_molecule_tab()
    with tabs[1]:
        render_route_tab()
    with tabs[2]:
        render_reaction_tab()
    with tabs[3]:
        render_gaussian_tab()
    with tabs[4]:
        render_kinetics_tab()
    with tabs[5]:
        render_adapters_tab(adapters)


def render_molecule_tab() -> None:
    st.subheader("分子摘要、RDKit 描述符与 OPERA 物性")
    left, right = st.columns([1, 2])
    with left:
        selected = st.selectbox("示例分子", list(DEMO_TARGETS), key="mol_demo")
        smiles = st.text_input("SMILES", DEMO_TARGETS[selected], key="mol_smiles")
        include_opera = st.checkbox("运行 OPERA QSAR", value=False)
        run = st.button("分析分子", type="primary")
    if not run:
        return

    with st.spinner("正在计算分子性质..."):
        summary = summarize_target_molecule(smiles)
        properties = predict_molecule_properties(smiles, include_opera=include_opera)
        descriptors = calculate_molecule_descriptors(smiles)

    with left:
        svg = molecule_svg(smiles)
        if svg:
            st.image(svg, use_container_width=True)
    with right:
        st.markdown("**基础摘要**")
        _dataframe(summary)
        st.markdown("**性质预测**")
        _json(properties)
        if descriptors.get("descriptors"):
            st.markdown("**描述符预览**")
            descriptor_rows = list(descriptors["descriptors"].items())[:80]
            st.dataframe(pd.DataFrame(descriptor_rows, columns=["descriptor", "value"]), use_container_width=True)


def render_route_tab() -> None:
    st.subheader("逆合成路线与报告")
    left, right = st.columns([1, 2])
    with left:
        target_name = st.selectbox("演示目标", ["Aspirin", "Paracetamol"], key="route_demo")
        smiles = st.text_input("目标 SMILES", DEMO_TARGETS[target_name], key="route_smiles")
        max_routes = st.slider("最多路线", min_value=1, max_value=5, value=3)
        use_aizynth = st.checkbox("尝试 AiZynthFinder", value=False)
        run = st.button("生成路线", type="primary")
    if not run:
        return

    with st.spinner("正在生成路线..."):
        result = analyze_target(smiles, demo_target=target_name, use_aizynth=use_aizynth, max_routes=max_routes)

    with left:
        _status(result["status"])
        st.download_button(
            "下载 Markdown 报告",
            data=result["report_markdown"],
            file_name="orgsynflow_route_report.md",
            mime="text/markdown",
        )
    with right:
        _dataframe(result["target"])
        render_route_cards(result)
        with st.expander("报告预览"):
            st.markdown(result["report_markdown"])


def render_route_cards(result: dict[str, Any]) -> None:
    scores = result.get("route_scores", {})
    feasibility = result.get("feasibility", {})
    for route in result.get("routes", []):
        score = scores.get(route["id"], {})
        feasible = feasibility.get(route["id"], {})
        title = f'{route["title"]} · 综合分 {score.get("route_score", "-")}'
        with st.expander(title, expanded=True):
            cols = st.columns(5)
            cols[0].metric("来源", route.get("source", "-"))
            cols[1].metric("步数", route.get("depth", "-"))
            cols[2].metric("前体", route.get("precursor_count", "-"))
            cols[3].metric("库存命中", route.get("stock_count", "-"))
            cols[4].metric("总收率", feasible.get("estimated_overall_yield_percent", "-"))
            _dataframe(score)
            st.markdown("**反应步骤**")
            st.dataframe(pd.DataFrame(route.get("steps", [])), use_container_width=True)


def render_reaction_tab() -> None:
    st.subheader("反应解释、原子映射、产率层级与反应特征")
    reaction_smiles = st.text_input("Reaction SMILES", SAMPLE_REACTION, key="reaction_smiles")
    template = st.text_input("反应模板/名称（可选）", "", key="reaction_template")
    if not st.button("分析反应", type="primary"):
        return

    template_value = template or None
    with st.spinner("正在分析反应..."):
        explanation = explain_single_reaction(reaction_smiles, template_value)
        mapping = map_single_reaction(reaction_smiles)
        ts_plan = plan_single_transition_state(reaction_smiles)
        yield_result = estimate_single_reaction_yield(reaction_smiles, template_value)
        features = calculate_reaction_features(reaction_smiles)

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**反应解释**")
        _json(explanation)
        st.markdown("**产率估计**")
        _json(yield_result)
    with cols[1]:
        st.markdown("**映射与反应中心**")
        _json(mapping)
        st.markdown("**反应特征**")
        _json(features)
    with st.expander("过渡态搜索计划", expanded=True):
        _json(ts_plan)


def render_gaussian_tab() -> None:
    st.subheader("Gaussian 状态、输入生成与日志解析")
    status = gaussian_status()
    _status("Gaussian 可用" if status.get("available") else "Gaussian 不可用")
    _dataframe(status)

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**生成 Gaussian 输入**")
        smiles = st.text_input("SMILES", "CCO", key="gaussian_smiles")
        job_type = st.text_input("Job type", "opt freq", key="gaussian_job")
        method = st.text_input("Method", "B3LYP", key="gaussian_method")
        basis = st.text_input("Basis", "6-31G(d)", key="gaussian_basis")
        if st.button("生成 gjf", type="primary"):
            gjf = make_gaussian_input(
                {
                    "smiles": smiles,
                    "job_type": job_type,
                    "method": method,
                    "basis": basis,
                    "title": "OrgSynFlow Gaussian job",
                    "charge": 0,
                    "multiplicity": 1,
                }
            )
            st.code(gjf, language="text")
            st.download_button("下载 gjf", data=gjf, file_name="orgsynflow_job.gjf", mime="text/plain")
    with cols[1]:
        st.markdown("**解析 Gaussian log/out 文本**")
        log_text = st.text_area("Gaussian log", SAMPLE_TS_LOG, height=260)
        if st.button("解析日志"):
            _json(parse_gaussian_text(log_text))


def render_kinetics_tab() -> None:
    st.subheader("ΔG、能垒与 Eyring 速率估算")
    cols = st.columns(3)
    reactant_log = cols[0].text_area("Reactant log", SAMPLE_REACTANT_LOG, height=260)
    ts_log = cols[1].text_area("TS log", SAMPLE_TS_LOG, height=260)
    product_log = cols[2].text_area("Product log", SAMPLE_PRODUCT_LOG, height=260)
    if not st.button("计算动力学", type="primary"):
        return

    profile = analyze_profile_from_logs(reactant_log, product_log, ts_log)
    metrics = st.columns(4)
    metrics[0].metric("ΔG_rxn kJ/mol", profile.get("delta_g_rxn_kj_mol"))
    metrics[1].metric("ΔG‡ kJ/mol", profile.get("delta_g_activation_kj_mol"))
    metrics[2].metric("k s^-1", profile.get("rate_constant_s_inv"))
    metrics[3].metric("TS 判据", "通过" if profile.get("ts_is_plausible") else "未通过")
    _json(profile)


def render_adapters_tab(adapters: list[dict[str, Any]]) -> None:
    st.subheader("外部工具适配器状态")
    rows = [
        {
            "name": item["name"],
            "display": item["display_name"],
            "available": item["available"],
            "status": item["status"],
            "source": item["source"],
            "reason": item["reason"],
        }
        for item in adapters
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with st.expander("完整适配器 JSON"):
        _json({"adapters": adapters})


def _render_top_metrics(adapters: list[dict[str, Any]]) -> None:
    available = sum(1 for item in adapters if item.get("available"))
    gaussian = gaussian_status()
    cols = st.columns(4)
    cols[0].metric("适配器可用", f"{available}/{len(adapters)}")
    cols[1].metric("Gaussian", "可用" if gaussian.get("available") else "不可用")
    cols[2].metric("路线引擎", "AiZynth/回退")
    cols[3].metric("前端", "Streamlit")


def _dataframe(data: Any) -> None:
    if hasattr(data, "as_display_dict"):
        data = data.as_display_dict()
    if isinstance(data, dict):
        rows = [{"field": key, "value": "" if value is None else str(value)} for key, value in data.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.dataframe(data, use_container_width=True)


def _json(data: Any) -> None:
    st.json(data, expanded=False)


def _status(message: str) -> None:
    lowered = message.lower()
    if any(token in lowered for token in ("unavailable", "failed", "not found", "不可用", "失败")):
        st.warning(message)
    else:
        st.success(message)


if __name__ == "__main__":
    main()
