from __future__ import annotations

import shutil

from adapters.base import AdapterCapability, AdapterStatus
from adapters.goodvibes_adapter import find_goodvibes_executable
from adapters.xtb_adapter import find_crest_executable, find_xtb_executable
from core.gaussian_runner import find_gaussian_executable
from core.molecule import has_rdkit


def list_adapter_statuses() -> list[AdapterStatus]:
    return [
        _rdkit_status(),
        _aizynth_status(),
        _gaussian_status(),
        _python_package_status(
            name="cclib",
            display_name="cclib",
            module_name="cclib",
            capability=AdapterCapability("quantum_log_parse", "解析 Gaussian/ORCA 等计算化学输出。"),
            source="Python import",
        ),
        _goodvibes_status(),
        _executable_status(
            name="opera",
            display_name="OPERA QSAR",
            executable_names=("opera", "OPERA", "OPERA.exe"),
            capability=AdapterCapability("property_prediction", "预测熔点、沸点、LogP、水溶解度等 QSAR 物性。"),
            source="OPERA CLI",
        ),
        _executable_status(
            name="xtb",
            display_name="xTB",
            executable_names=("xtb", "xtb.exe"),
            capability=AdapterCapability("semiempirical_qc", "半经验量化预优化、能量与快速构象评估。"),
            source="xTB CLI",
            detected_executable=find_xtb_executable(),
        ),
        _executable_status(
            name="crest",
            display_name="CREST",
            executable_names=("crest", "crest.exe"),
            capability=AdapterCapability("conformer_search", "基于 xTB 的构象搜索与转子搜索。"),
            source="CREST CLI",
            detected_executable=find_crest_executable(),
        ),
        _python_package_status(
            name="rxnmapper",
            display_name="RXNMapper",
            module_name="rxnmapper",
            capability=AdapterCapability("reaction_mapping", "为 reaction SMILES 生成原子映射并辅助反应中心识别。"),
            source="Python import",
        ),
        _python_package_status(
            name="drfp",
            display_name="DRFP",
            module_name="drfp",
            capability=AdapterCapability("reaction_features", "生成反应差分指纹，供产率或分类模型使用。"),
            source="Python import",
        ),
    ]


def adapter_status_map() -> dict[str, AdapterStatus]:
    return {status.name: status for status in list_adapter_statuses()}


def _rdkit_status() -> AdapterStatus:
    available = has_rdkit()
    return AdapterStatus(
        name="rdkit",
        display_name="RDKit",
        available=available,
        status="available" if available else "unavailable",
        reason=None if available else "当前 Python 环境无法导入 RDKit。",
        capabilities=[
            AdapterCapability("molecule_validation", "SMILES 解析、规范化与基础分子校验。"),
            AdapterCapability("molecular_descriptors", "分子式、分子量、LogP、TPSA、氢键供受体等基础描述符。"),
            AdapterCapability("structure_drawing", "生成分子 SVG 结构图。"),
        ],
        source="Python import",
        confidence="runtime_import",
    )


def _aizynth_status() -> AdapterStatus:
    executable = shutil.which("aizynthcli")
    return AdapterStatus(
        name="aizynthfinder",
        display_name="AiZynthFinder",
        available=executable is not None,
        status="available" if executable else "unavailable",
        reason=None if executable else "未在 PATH 中检测到 aizynthcli；路线预测会回退到内置 demo。",
        capabilities=[
            AdapterCapability("retrosynthesis", "从目标分子预测逆合成路线并尝试分解到库存原料。"),
        ],
        source="aizynthcli",
        confidence="path_probe",
        metadata={"executable": executable},
    )


def _gaussian_status() -> AdapterStatus:
    executable = find_gaussian_executable()
    return AdapterStatus(
        name="gaussian",
        display_name="Gaussian",
        available=executable is not None,
        status="available" if executable else "unavailable",
        reason=None if executable else "未检测到 g16/g09/gaussian 可执行文件；只能生成输入文件和解析已有 log。",
        capabilities=[
            AdapterCapability("quantum_chemistry", "运行 Gaussian opt/freq/TS 等量化计算。"),
            AdapterCapability("gaussian_input", "从 SMILES 生成 Gaussian 输入文本。"),
            AdapterCapability("gaussian_log_parse", "解析 Gaussian log/out 中的能量、自由能、虚频和轨道信息。"),
        ],
        source="Gaussian executable",
        confidence="path_probe",
        metadata={"executable": executable},
    )


def _executable_status(
    name: str,
    display_name: str,
    executable_names: tuple[str, ...],
    capability: AdapterCapability,
    source: str,
    detected_executable: str | None = None,
) -> AdapterStatus:
    executable = detected_executable or next((found for candidate in executable_names if (found := shutil.which(candidate))), None)
    return AdapterStatus(
        name=name,
        display_name=display_name,
        available=executable is not None,
        status="available" if executable else "unavailable",
        reason=None if executable else f"未在 PATH 中检测到 {display_name}；该能力将在后续阶段作为可选适配器接入。",
        capabilities=[capability],
        source=source,
        confidence="path_probe",
        metadata={"executable": executable},
    )


def _goodvibes_status() -> AdapterStatus:
    executable = find_goodvibes_executable()
    return AdapterStatus(
        name="goodvibes",
        display_name="GoodVibes",
        available=executable is not None,
        status="available" if executable else "unavailable",
        reason=None if executable else "未在 PATH 中检测到 GoodVibes；热化学校正作为可选能力保留。",
        capabilities=[
            AdapterCapability("thermochemistry_correction", "对 Gaussian log 进行准谐振热化学校正。"),
        ],
        source="GoodVibes CLI",
        confidence="path_probe",
        metadata={"executable": executable},
    )


def _python_package_status(
    name: str,
    display_name: str,
    module_name: str,
    capability: AdapterCapability,
    source: str,
) -> AdapterStatus:
    try:
        __import__(module_name)
    except Exception as exc:
        return AdapterStatus(
            name=name,
            display_name=display_name,
            available=False,
            status="unavailable",
            reason=f"当前 Python 环境无法导入 {module_name}：{exc}",
            capabilities=[capability],
            source=source,
            confidence="runtime_import",
        )
    return AdapterStatus(
        name=name,
        display_name=display_name,
        available=True,
        status="available",
        reason=None,
        capabilities=[capability],
        source=source,
        confidence="runtime_import",
    )
