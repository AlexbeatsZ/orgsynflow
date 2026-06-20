from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class ReactionExplanation:
    reaction_smiles: str
    reaction_type: str
    formed_bonds: list[str]
    broken_bonds: list[str]
    reaction_center: list[str]
    summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "reaction_smiles": self.reaction_smiles,
            "reaction_type": self.reaction_type,
            "formed_bonds": self.formed_bonds,
            "broken_bonds": self.broken_bonds,
            "reaction_center": self.reaction_center,
            "summary": self.summary,
        }


def explain_reaction(reaction_smiles: str | None, template: str | None = None) -> ReactionExplanation:
    text = f"{reaction_smiles or ''} {template or ''}".lower()
    rxn = reaction_smiles or ""

    if any(keyword in text for keyword in ("acetylation", "acylation", "酰化", "乙酰化")):
        if "n" in _product_part(rxn).lower():
            return ReactionExplanation(
                reaction_smiles=rxn,
                reaction_type="酰化/乙酰化",
                formed_bonds=["C-N"],
                broken_bonds=["酸酐 C-O"],
                reaction_center=["酰基碳", "胺氮"],
                summary="胺氮作为亲核中心进攻酸酐酰基碳，形成酰胺键；该步骤可视为亲核取代型乙酰化。",
            )
        return ReactionExplanation(
            reaction_smiles=rxn,
            reaction_type="酰化/乙酰化",
            formed_bonds=["C-O"],
            broken_bonds=["酸酐 C-O"],
            reaction_center=["酰基碳", "酚羟基氧"],
            summary="酚羟基氧作为亲核中心进攻酸酐酰基碳，形成酯键；该步骤可视为亲核取代型乙酰化。",
        )

    if any(keyword in text for keyword in ("hydrolysis", "水解")):
        return ReactionExplanation(
            reaction_smiles=rxn,
            reaction_type="酯水解",
            formed_bonds=["C-OH"],
            broken_bonds=["C-O"],
            reaction_center=["酯羰基碳", "离去烷氧基"],
            summary="酯羰基被水或氢氧根进攻，烷氧基离去，最终生成羧酸或羧酸盐。",
        )

    if ">>" not in rxn:
        return ReactionExplanation(
            reaction_smiles=rxn,
            reaction_type="未知",
            formed_bonds=[],
            broken_bonds=[],
            reaction_center=[],
            summary="缺少标准 reaction SMILES，当前只能保留为待解释步骤。",
        )

    return ReactionExplanation(
        reaction_smiles=rxn,
        reaction_type="通用转化",
        formed_bonds=["待原子映射确认"],
        broken_bonds=["待原子映射确认"],
        reaction_center=["反应物与产物结构差异区域"],
        summary="基于反应结构差异进行解释。",
    )


def _product_part(reaction_smiles: str) -> str:
    if ">>" not in reaction_smiles:
        return ""
    return reaction_smiles.split(">>", 1)[1]


def explain_reaction_with_deepseek(
    reaction_smiles: str,
    template: str | None = None,
    fallback_explanation: ReactionExplanation | None = None,
) -> dict[str, object]:
    api_key = _get_deepseek_key()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if not api_key:
        return {
            "available": False,
            "method": "deepseek_chat_completion",
            "reason": "DEEPSEEK_API_KEY 未配置。",
            "explanation": (fallback_explanation or explain_reaction(reaction_smiles, template)).as_dict(),
        }

    prompt = {
        "reaction_smiles": reaction_smiles,
        "template": template,
        "rule_explanation": (fallback_explanation or explain_reaction(reaction_smiles, template)).as_dict(),
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
                            "你是有机合成化学专家。请基于给定 reaction SMILES 和模板信息，"
                            "分析反应类型、形成的化学键、断裂的化学键、反应中心，并给出反应机理摘要。"
                            "只输出 JSON，不输出 Markdown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请分析该反应并输出 JSON："
                            "reaction_type(字符串), formed_bonds(字符串数组), broken_bonds(字符串数组), "
                            "reaction_center(字符串数组), summary(详细机理说明字符串)。输入如下：\n"
                            f"{json.dumps(prompt, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0.2,
                "max_tokens": 1000,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        content = str(payload["choices"][0]["message"]["content"])
        parsed = _parse_json(content)
        return {
            "available": True,
            "method": f"deepseek_chat_completion:{model}",
            "explanation": {
                "reaction_smiles": reaction_smiles,
                "reaction_type": str(parsed.get("reaction_type") or "通用转化"),
                "formed_bonds": _str_list(parsed.get("formed_bonds")),
                "broken_bonds": _str_list(parsed.get("broken_bonds")),
                "reaction_center": _str_list(parsed.get("reaction_center")),
                "summary": str(parsed.get("summary") or "AI 分析已完成。"),
            },
        }
    except Exception as exc:
        return {
            "available": False,
            "method": f"deepseek_chat_completion:{model}",
            "reason": f"DeepSeek 调用失败。错误类型：{type(exc).__name__}",
            "explanation": (fallback_explanation or explain_reaction(reaction_smiles, template)).as_dict(),
        }


def _get_deepseek_key() -> str | None:
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


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
