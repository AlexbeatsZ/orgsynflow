from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from services.workbench import (
    analyze_target,
    calculate_molecule_descriptors,
    calculate_reaction_features,
    estimate_single_reaction_yield,
    gaussian_status,
    list_adapters,
    make_gaussian_input,
    map_single_reaction,
    plan_single_transition_state,
    predict_molecule_properties,
    analyze_profile_from_logs,
    explain_single_reaction,
    summarize_target_molecule,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = args.handler(args)
    _emit(payload, getattr(args, "format", "text"))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OrgSynFlow command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health", help="检查 OrgSynFlow CLI 是否可用")
    health.add_argument("--format", choices=("text", "json"), default="text")
    health.set_defaults(handler=_health)

    adapters = subparsers.add_parser("adapters", help="列出外部工具适配器可用性")
    adapters.add_argument("--format", choices=("text", "json"), default="text")
    adapters.set_defaults(handler=_adapters)

    molecule = subparsers.add_parser("molecule", help="解析 SMILES 并输出基础分子性质")
    molecule.add_argument("smiles")
    molecule.add_argument("--format", choices=("text", "json"), default="text")
    molecule.set_defaults(handler=_molecule)

    route = subparsers.add_parser("route", help="预测或加载目标分子的合成路线")
    route.add_argument("smiles")
    route.add_argument("--demo-target", default="Aspirin", choices=("Aspirin", "Paracetamol"))
    route.add_argument("--max-routes", type=int, default=3)
    route.add_argument("--use-aizynth", action="store_true")
    route.add_argument("--aizynth-config")
    route.add_argument("--aizynth-stock")
    route.add_argument("--aizynth-policy")
    route.add_argument("--format", choices=("text", "json"), default="text")
    route.set_defaults(handler=_route)

    properties = subparsers.add_parser("properties", help="输出 RDKit 基础性质和可选 OPERA QSAR 预测")
    properties.add_argument("smiles")
    properties.add_argument("--include-opera", action="store_true")
    properties.add_argument("--format", choices=("text", "json"), default="text")
    properties.set_defaults(handler=_properties)

    descriptors = subparsers.add_parser("descriptors", help="输出 RDKit/Mordred 描述符")
    descriptors.add_argument("smiles")
    descriptors.add_argument("--format", choices=("text", "json"), default="text")
    descriptors.set_defaults(handler=_descriptors)

    gaussian_status_parser = subparsers.add_parser("gaussian-status", help="检查 Gaussian 可执行文件")
    gaussian_status_parser.add_argument("--format", choices=("text", "json"), default="text")
    gaussian_status_parser.set_defaults(handler=_gaussian_status)

    gaussian_input = subparsers.add_parser("gaussian-input", help="从 SMILES 生成 Gaussian 输入文本")
    gaussian_input.add_argument("smiles")
    gaussian_input.add_argument("--title", default="OrgSynFlow Gaussian job")
    gaussian_input.add_argument("--method", default="B3LYP")
    gaussian_input.add_argument("--basis", default="6-31G(d)")
    gaussian_input.add_argument("--job-type", default="opt freq")
    gaussian_input.add_argument("--charge", type=int, default=0)
    gaussian_input.add_argument("--multiplicity", type=int, default=1)
    gaussian_input.add_argument("--format", choices=("text", "json"), default="text")
    gaussian_input.set_defaults(handler=_gaussian_input)

    reaction_explain = subparsers.add_parser("reaction-explain", help="解释单步 reaction SMILES")
    reaction_explain.add_argument("reaction_smiles")
    reaction_explain.add_argument("--template")
    reaction_explain.add_argument("--format", choices=("text", "json"), default="text")
    reaction_explain.set_defaults(handler=_reaction_explain)

    reaction_map = subparsers.add_parser("reaction-map", help="用 RXNMapper 或规则 fallback 生成反应映射摘要")
    reaction_map.add_argument("reaction_smiles")
    reaction_map.add_argument("--format", choices=("text", "json"), default="text")
    reaction_map.set_defaults(handler=_reaction_map)

    ts_plan = subparsers.add_parser("ts-plan", help="生成半自动过渡态搜索计划")
    ts_plan.add_argument("reaction_smiles")
    ts_plan.add_argument("--format", choices=("text", "json"), default="text")
    ts_plan.set_defaults(handler=_ts_plan)

    kinetics = subparsers.add_parser("kinetics", help="从 Gaussian log 计算反应热力学和 Eyring 速率")
    kinetics.add_argument("--reactant-log", required=True)
    kinetics.add_argument("--ts-log", required=True)
    kinetics.add_argument("--product-log", required=True)
    kinetics.add_argument("--format", choices=("text", "json"), default="text")
    kinetics.set_defaults(handler=_kinetics)

    yield_parser = subparsers.add_parser("yield", help="输出分层产率估计")
    yield_parser.add_argument("reaction_smiles")
    yield_parser.add_argument("--template")
    yield_parser.add_argument("--format", choices=("text", "json"), default="text")
    yield_parser.set_defaults(handler=_yield)

    reaction_features = subparsers.add_parser("reaction-features", help="输出反应指纹或 fallback 特征")
    reaction_features.add_argument("reaction_smiles")
    reaction_features.add_argument("--format", choices=("text", "json"), default="text")
    reaction_features.set_defaults(handler=_reaction_features)

    return parser


def _health(args: argparse.Namespace) -> dict[str, object]:
    return {
        "status": "ok",
        "version": "V6",
        "source": "orgsynflow-cli",
    }


def _adapters(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "adapter_registry",
        "adapters": list_adapters(),
    }


def _molecule(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "rdkit",
        "molecule": summarize_target_molecule(args.smiles),
    }


def _route(args: argparse.Namespace) -> dict[str, object]:
    result = analyze_target(
        args.smiles,
        demo_target=args.demo_target,
        use_aizynth=args.use_aizynth,
        max_routes=args.max_routes,
        aizynth_config=args.aizynth_config,
        aizynth_stock=args.aizynth_stock,
        aizynth_policy=args.aizynth_policy,
    )
    return {
        "source": "workbench",
        "status": result["status"],
        "target": result["target"],
        "routes": result["routes"],
        "route_scores": result["route_scores"],
        "feasibility": result["feasibility"],
    }


def _properties(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "property_service",
        **predict_molecule_properties(args.smiles, include_opera=args.include_opera),
    }


def _descriptors(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "descriptor_service",
        **calculate_molecule_descriptors(args.smiles),
    }


def _gaussian_status(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "gaussian_runner",
        **gaussian_status(),
    }


def _gaussian_input(args: argparse.Namespace) -> dict[str, object]:
    gjf = make_gaussian_input(
        {
            "smiles": args.smiles,
            "title": args.title,
            "method": args.method,
            "basis": args.basis,
            "job_type": args.job_type,
            "charge": args.charge,
            "multiplicity": args.multiplicity,
        }
    )
    return {
        "source": "gaussian_input_generator",
        "gjf": gjf,
    }


def _reaction_explain(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "reaction_explain",
        **explain_single_reaction(args.reaction_smiles, args.template),
    }


def _reaction_map(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "reaction_mapping",
        **map_single_reaction(args.reaction_smiles),
    }


def _ts_plan(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "transition_state_planner",
        **plan_single_transition_state(args.reaction_smiles),
    }


def _kinetics(args: argparse.Namespace) -> dict[str, object]:
    from pathlib import Path

    return {
        "source": "kinetics_service",
        **analyze_profile_from_logs(
            Path(args.reactant_log).read_text(encoding="utf-8", errors="ignore"),
            Path(args.product_log).read_text(encoding="utf-8", errors="ignore"),
            Path(args.ts_log).read_text(encoding="utf-8", errors="ignore"),
        ),
    }


def _yield(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "yield_service",
        **estimate_single_reaction_yield(args.reaction_smiles, args.template),
    }


def _reaction_features(args: argparse.Namespace) -> dict[str, object]:
    return {
        "source": "reaction_feature_service",
        **calculate_reaction_features(args.reaction_smiles),
    }


def _emit(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    if "adapters" in payload:
        print("OrgSynFlow 适配器状态")
        for item in payload["adapters"]:
            marker = "可用" if item["available"] else "不可用"
            reason = f"；{item['reason']}" if item.get("reason") else ""
            print(f"- {item['display_name']} ({item['name']}): {marker}{reason}")
        return

    if "molecule" in payload:
        molecule = payload["molecule"]
        print("分子摘要")
        for key, value in molecule.items():
            print(f"- {key}: {value}")
        return

    if "rdkit" in payload:
        print("分子性质")
        print("RDKit 描述符：")
        for key, value in payload["rdkit"].items():
            print(f"- {key}: {value}")
        opera = payload.get("opera")
        if opera:
            print("OPERA QSAR：")
            print(f"- 状态: {opera['status']}")
            if opera.get("reason"):
                print(f"- 原因: {opera['reason']}")
            for key, value in opera.get("properties", {}).items():
                print(f"- {key}: {value}")
        print(f"说明：{payload['note']}")
        return

    if "descriptors" in payload:
        print("分子描述符")
        for key, value in payload["descriptors"].items():
            print(f"- {key}: {value}")
        unavailable = payload.get("unavailable") or []
        if unavailable:
            print(f"不可用增强项：{', '.join(unavailable)}")
        return

    if "routes" in payload:
        print(f"路线状态：{payload['status']}")
        print("目标分子：")
        for key, value in payload["target"].items():
            print(f"- {key}: {value}")
        print("候选路线：")
        for route in payload["routes"]:
            print(f"- {route['title']} ({route['source']}): {len(route['steps'])} 步")
        return

    if "gjf" in payload:
        print(payload["gjf"])
        return

    if "reaction_type" in payload:
        print(f"反应类型：{payload['reaction_type']}")
        print(f"反应中心：{'、'.join(payload['reaction_center'])}")
        print(f"说明：{payload['summary']}")
        if "yield_estimate" in payload:
            print(f"启发式产率：{payload['yield_estimate']['heuristic_yield_percent']}%")
        return

    if "mapped_reaction_smiles" in payload:
        print(f"映射状态：{payload['status']}")
        print(f"方法：{payload['method']}")
        print(f"置信度：{payload['confidence']}")
        print(f"映射 reaction SMILES：{payload['mapped_reaction_smiles'] or '-'}")
        print(f"说明：{payload['note']}")
        return

    if "validation_level" in payload:
        print(f"TS 搜索状态：{payload['status']} / {payload['validation_level']}")
        print(f"Scan route：{payload['gaussian_scan_route']}")
        print(f"TS route：{payload['gaussian_ts_route']}")
        print(f"IRC route：{payload['gaussian_irc_route']}")
        for warning in payload["warnings"]:
            print(f"警告：{warning}")
        return

    if "delta_g_rxn_kj_mol" in payload:
        print("动力学/热力学摘要")
        print(f"- dG_rxn: {payload['delta_g_rxn_kj_mol']} kJ/mol")
        print(f"- dG_activation: {payload['delta_g_activation_kj_mol']} kJ/mol")
        print(f"- k: {payload['rate_constant_s_inv']} s^-1")
        print(f"- 判定: {payload['verdict']}")
        return

    if "heuristic" in payload and "trained_model" in payload:
        heuristic = payload["heuristic"]
        print("分层产率估计")
        print(f"- 方法: {payload['method']}")
        print(f"- 状态: {payload['status']}")
        print(f"- 启发式产率: {heuristic['heuristic_yield_percent']}%")
        print(f"- 置信度: {payload['confidence']}")
        print(f"- 适用域: {payload['applicability_domain']}")
        print(f"- 说明: {payload['note']}")
        return

    if "features" in payload and "applicability_domain" in payload:
        print("反应特征")
        print(f"- 方法: {payload['method']}")
        print(f"- 状态: {payload['status']}")
        print(f"- 特征数量: {len(payload['features'])}")
        print(f"- 适用域: {payload['applicability_domain']}")
        if payload.get("note"):
            print(f"- 说明: {payload['note']}")
        return

    if "available" in payload and "executable" in payload:
        print(f"Gaussian 可用：{payload['available']}")
        print(f"可执行文件：{payload['executable'] or '-'}")
        return

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
