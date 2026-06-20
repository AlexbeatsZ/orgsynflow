from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from core.reaction_explain import explain_reaction


@dataclass(frozen=True)
class ReactionMapping:
    reaction_smiles: str
    mapped_reaction_smiles: str | None
    method: str
    status: str
    confidence: str
    reaction_center: list[str]
    formed_bonds: list[str]
    broken_bonds: list[str]
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "reaction_smiles": self.reaction_smiles,
            "mapped_reaction_smiles": self.mapped_reaction_smiles,
            "method": self.method,
            "status": self.status,
            "confidence": self.confidence,
            "reaction_center": self.reaction_center,
            "formed_bonds": self.formed_bonds,
            "broken_bonds": self.broken_bonds,
            "note": self.note,
        }


def _map_reaction_via_wsl(reaction_smiles: str) -> dict[str, object] | None:
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    python_exe = "/home/meta/.local/opt/miniforge3/envs/orgsynflow-chem/bin/python"
    py_script = f"""
import json, sys
try:
    from rxnmapper import RXNMapper
    mapper = RXNMapper()
    res = mapper.get_attention_guided_atom_maps([{repr(reaction_smiles)}])[0]
    print(json.dumps({{"status": "success", "data": res}}))
except Exception as exc:
    print(json.dumps({{"status": "error", "error": str(exc)}}))
"""
    try:
        completed = subprocess.run(
            [wsl, "-e", python_exe, "-c", py_script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            for line in completed.stdout.splitlines():
                if line.strip().startswith("{") and line.strip().endswith("}"):
                    payload = json.loads(line)
                    if payload.get("status") == "success":
                        return payload["data"]
    except Exception:
        pass
    return None


def map_reaction(reaction_smiles: str) -> ReactionMapping:
    # 1. Try local RXNMapper first
    local_mapped = None
    local_err = None
    try:
        from rxnmapper import RXNMapper
        local_mapped = RXNMapper().get_attention_guided_atom_maps([reaction_smiles])[0]
        method = "rxnmapper_local"
    except Exception as exc:
        local_err = exc

    # 2. If local fails, try WSL bridge
    result = None
    if local_mapped:
        result = local_mapped
    else:
        result = _map_reaction_via_wsl(reaction_smiles)
        method = "rxnmapper_wsl" if result else "heuristic_without_rxnmapper"

    if not result or method == "heuristic_without_rxnmapper":
        explanation = explain_reaction(reaction_smiles)
        err_msg = f"本地: {local_err}; WSL未返回结果" if local_err else "WSL未返回结果"
        return ReactionMapping(
            reaction_smiles=reaction_smiles,
            mapped_reaction_smiles=None,
            method="heuristic_without_rxnmapper",
            status="unavailable",
            confidence="低",
            reaction_center=explanation.reaction_center,
            formed_bonds=explanation.formed_bonds,
            broken_bonds=explanation.broken_bonds,
            note=f"未能在本地或WSL环境成功调用 RXNMapper ({err_msg})；当前返回规则估计反应中心。",
        )

    explanation = explain_reaction(reaction_smiles)
    confidence_score = float(result.get("confidence", 0.0) or 0.0)
    confidence = "高" if confidence_score >= 0.8 else "中" if confidence_score >= 0.5 else "低"
    return ReactionMapping(
        reaction_smiles=reaction_smiles,
        mapped_reaction_smiles=result.get("mapped_rxn"),
        method=method,
        status="mapped",
        confidence=confidence,
        reaction_center=explanation.reaction_center,
        formed_bonds=explanation.formed_bonds,
        broken_bonds=explanation.broken_bonds,
        note=f"已通过 {method} 运行 RXNMapper (confidence={confidence_score:.3f})；成键/断键已成功识别。",
    )


def mapped_atom_coordinates(mapped_reaction_smiles: str) -> dict[str, object]:
    parts = mapped_reaction_smiles.split(">>")
    if len(parts) != 2:
        return {"error": "reaction SMILES 缺少 >> 分隔符"}

    reactant_data = _parse_mapped_side(parts[0])
    product_data = _parse_mapped_side(parts[1])

    return {
        "reactants": reactant_data,
        "products": product_data,
    }


def _parse_mapped_side(smiles: str) -> dict[str, object]:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"error": f"无法解析 SMILES", "xyz": "", "atoms": []}

    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 20260614
    if AllChem.EmbedMolecule(mol, params) != 0:
        return {"error": "3D 构象生成失败", "xyz": "", "atoms": []}
    AllChem.UFFOptimizeMolecule(mol, maxIters=200)

    conf = mol.GetConformer()
    atoms_out: list[dict[str, object]] = []
    xyz_lines: list[str] = []

    for atom in mol.GetAtoms():
        idx = atom.GetIdx()
        pos = conf.GetAtomPosition(idx)
        elem = atom.GetSymbol()
        map_num = atom.GetAtomMapNum()
        x, y, z = pos.x, pos.y, pos.z
        xyz_lines.append(f"{elem:<2} {x:>12.6f} {y:>12.6f} {z:>12.6f}")
        atoms_out.append({
            "element": elem,
            "x": round(x, 6),
            "y": round(y, 6),
            "z": round(z, 6),
            "map_index": map_num,
        })

    xyz = f"{len(atoms_out)}\n{smiles}\n" + "\n".join(xyz_lines) + "\n"
    return {"xyz": xyz, "atoms": atoms_out}


def correct_mapping_with_deepseek(
    reaction_smiles: str,
    mapping: ReactionMapping | None = None,
) -> dict[str, object]:
    api_key = _get_ds_key()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if not mapping:
        mapping = map_reaction(reaction_smiles)

    if not api_key:
        return {
            "available": False,
            "method": "deepseek_chat_completion",
            "reason": "DEEPSEEK_API_KEY 未配置。",
            **mapping.as_dict(),
        }

    prompt = {
        "reaction_smiles": reaction_smiles,
        "rxn_mapped_smiles": mapping.mapped_reaction_smiles,
        "rxn_confidence": mapping.confidence,
    }
    try:
        response = httpx.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是有机化学反应专家。请校验 RXNMapper 生成的原子映射是否正确，"
                            "特别注意检查反应中是否丢失了小分子（如 H2O, HCl, NH3, HBr, CO2, N2, "
                            "NaCl, H2SO4, NaOH, MeOH, EtOH, AcOH 等副产物）。"
                            "如果原 mapped_rxn 缺少小分子产物，请在产物侧补充并以原子映射编号标注。"
                            "只输出 JSON，不输出 Markdown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请校验以下反应的原子映射并输出 JSON："
                            "mapped_reaction_smiles(字符串, 修正后的完整映射 SMILES), "
                            "has_corrections(布尔值), corrections(字符串数组, 描述做了哪些修正), "
                            "missing_small_molecules(字符串数组, 被 RXNMapper 遗漏的小分子), "
                            "confidence(低/中/高字符串)。输入如下：\n"
                            f"{json.dumps(prompt, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        content = str(payload["choices"][0]["message"]["content"])
        parsed = _parse_ds_json(content)

        corrected_smiles = str(parsed.get("mapped_reaction_smiles") or mapping.mapped_reaction_smiles or "")
        confidence = str(parsed.get("confidence") or mapping.confidence)
        if confidence not in {"低", "中", "高"}:
            confidence = mapping.confidence

        corrections = _ds_str_list(parsed.get("corrections"))
        missing = _ds_str_list(parsed.get("missing_small_molecules"))

        return {
            "available": True,
            "method": f"deepseek_chat_completion:{model}",
            "reaction_smiles": mapping.reaction_smiles,
            "mapped_reaction_smiles": corrected_smiles if corrected_smiles else mapping.mapped_reaction_smiles,
            "confidence": "高" if parsed.get("has_corrections") else confidence,
            "status": "mapped_corrected" if parsed.get("has_corrections") else mapping.status,
            "reaction_center": mapping.reaction_center,
            "formed_bonds": mapping.formed_bonds,
            "broken_bonds": mapping.broken_bonds,
            "has_corrections": bool(parsed.get("has_corrections")),
            "corrections": corrections,
            "missing_small_molecules": missing,
            "note": f"AI 已校验映射{'并修正' if parsed.get('has_corrections') else ''}。"
                    + (f" 补充了遗漏小分子: {', '.join(missing)}。" if missing else ""),
        }
    except Exception as exc:
        return {
            "available": False,
            "method": f"deepseek_chat_completion:{model}",
            "reason": f"DeepSeek 调用失败。错误类型：{type(exc).__name__}",
            **mapping.as_dict(),
        }


def _get_ds_key() -> str | None:
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key
    root = Path(__file__).resolve().parents[1]
    for filename in (".env.local", ".env"):
        path = root / filename
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "DEEPSEEK_API_KEY":
                return v.strip().strip("\"'")
    return None


def _parse_ds_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _ds_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
