from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from services.workbench import (
    analyze_target,
    gaussian_status,
    list_adapters,
    make_gaussian_input,
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
    route.add_argument("--format", choices=("text", "json"), default="text")
    route.set_defaults(handler=_route)

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
    )
    return {
        "source": "workbench",
        "status": result["status"],
        "target": result["target"],
        "routes": result["routes"],
        "route_scores": result["route_scores"],
        "feasibility": result["feasibility"],
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


def _emit(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
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

    if "available" in payload and "executable" in payload:
        print(f"Gaussian 可用：{payload['available']}")
        print(f"可执行文件：{payload['executable'] or '-'}")
        return

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
