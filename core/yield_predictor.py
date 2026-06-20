from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from core.reaction_explain import explain_reaction
from core.reaction_features import featurize_reaction
from core.route import Route


@dataclass(frozen=True)
class YieldEstimate:
    heuristic_yield_percent: float
    confidence: str
    factors: list[str]
    note: str
    method: str = "heuristic_rules"
    applicability_domain: str = "规则启发式。"

    def as_dict(self) -> dict[str, object]:
        return {
            "heuristic_yield_percent": self.heuristic_yield_percent,
            "predicted_yield_percent": self.heuristic_yield_percent,
            "method": self.method,
            "confidence": self.confidence,
            "applicability_domain": self.applicability_domain,
            "factors": self.factors,
            "note": self.note,
        }


@dataclass(frozen=True)
class RouteFeasibility:
    route_id: str
    heuristic_overall_yield_percent: float
    heuristic_feasibility_score: float
    risk_flags: list[str]
    note: str
    method: str = "heuristic_route_feasibility"
    applicability_domain: str = "规则启发式。"

    def as_dict(self) -> dict[str, object]:
        return {
            "route_id": self.route_id,
            "heuristic_overall_yield_percent": self.heuristic_overall_yield_percent,
            "heuristic_feasibility_score": self.heuristic_feasibility_score,
            "estimated_overall_yield_percent": self.heuristic_overall_yield_percent,
            "route_feasibility_score": self.heuristic_feasibility_score,
            "method": self.method,
            "applicability_domain": self.applicability_domain,
            "risk_flags": self.risk_flags,
            "note": self.note,
        }


def estimate_reaction_yield(reaction_smiles: str | None, template: str | None = None) -> YieldEstimate:
    explanation = explain_reaction(reaction_smiles, template)
    factors: list[str] = []
    base = 62.0
    confidence = "低"

    if explanation.reaction_type == "酰化/乙酰化":
        base = 78.0
        confidence = "中"
        factors.append("乙酰化通常是教学演示中较稳健的官能团转化。")
    elif explanation.reaction_type == "酯水解":
        base = 70.0
        confidence = "中"
        factors.append("酯水解条件成熟，但实际收率受酸碱条件和后处理影响。")
    else:
        factors.append("当前反应类型未匹配到专门规则。")

    text = f"{reaction_smiles or ''} {template or ''}".lower()
    if any(flag in text for flag in ("cl", "br", "i")):
        base -= 5.0
        factors.append("存在卤素或潜在离去基，需关注副反应。")
    if "." in (reaction_smiles or "").split(">>", 1)[0]:
        base += 3.0
        factors.append("多组分前体明确，适合做单步路线验证。")

    return YieldEstimate(
        heuristic_yield_percent=round(max(5.0, min(base, 95.0)), 1),
        confidence=confidence,
        factors=factors,
        note="规则估计。",
    )


def estimate_reaction_yield_layered(
    reaction_smiles: str | None,
    template: str | None = None,
    use_llm_fallback: bool = False,
) -> dict[str, object]:
    rxn = reaction_smiles or ""
    heuristic = estimate_reaction_yield(rxn, template)
    features = featurize_reaction(rxn).as_dict() if rxn else {
        "status": "unavailable",
        "method": "none",
        "features": {},
        "applicability_domain": "缺少 reaction SMILES。",
        "unavailable": ["reaction_smiles"],
        "note": "无法生成反应特征。",
    }

    has_model = False
    model_method = "chemprop_or_rxn_yields_placeholder"
    model_reason = "当前未配置训练好的产率模型权重；不会输出伪 ML 产率。"
    model_yield = None

    result: dict[str, object] = {
        "method": "layered_heuristic_plus_optional_features",
        "status": "heuristic_only" if features["status"] != "available" else "features_available",
        "heuristic": heuristic.as_dict(),
        "ml_features": features,
        "trained_model": {
            "available": has_model,
            "method": model_method,
            "reason": model_reason,
            "predicted_yield": model_yield,
        },
        "confidence": heuristic.confidence,
        "applicability_domain": heuristic.applicability_domain,
        "note": "产率采用分层输出。",
    }
    if use_llm_fallback:
        result["llm_estimate"] = estimate_reaction_yield_with_deepseek(rxn, template, heuristic, features)
    return result


def estimate_reaction_yield_with_deepseek(
    reaction_smiles: str,
    template: str | None,
    heuristic: YieldEstimate | None = None,
    features: dict[str, object] | None = None,
) -> dict[str, object]:
    heuristic = heuristic or estimate_reaction_yield(reaction_smiles, template)
    api_key = _deepseek_api_key()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if not api_key:
        return {
            "available": False,
            "method": "deepseek_chat_completion",
            "reason": "DEEPSEEK_API_KEY 未配置。",
            "applicability_domain": "无 LLM 调用。",
        }

    prompt = {
        "reaction_smiles": reaction_smiles,
        "template": template,
        "heuristic_baseline": heuristic.as_dict(),
        "reaction_features": features or {},
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
                            "你是有机合成信息学助手。请基于给定 reaction SMILES、模板、启发式基线和可用反应特征，"
                            "给出反应产率估算。只输出 JSON，不输出 Markdown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请估算该反应的单步分离产率，并输出："
                            "predicted_yield_percent(0-100数字), confidence(低/中/高), "
                            "factors(字符串数组), risks(字符串数组), recommendations(字符串数组), "
                            "applicability_domain(字符串)。输入如下：\n"
                            f"{json.dumps(prompt, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0.1,
                "max_tokens": 900,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        content = str(payload["choices"][0]["message"]["content"])
        parsed = _parse_llm_json(content)
        predicted = _clamp_float(parsed.get("predicted_yield_percent"), 0.0, 100.0, heuristic.heuristic_yield_percent)
        confidence = str(parsed.get("confidence") or heuristic.confidence)
        if confidence not in {"低", "中", "高"}:
            confidence = heuristic.confidence
        return {
            "available": True,
            "method": f"deepseek_chat_completion:{model}",
            "predicted_yield_percent": round(predicted, 1),
            "confidence": confidence,
            "factors": _string_list(parsed.get("factors")),
            "risks": _string_list(parsed.get("risks")),
            "recommendations": _string_list(parsed.get("recommendations")),
            "applicability_domain": str(
                parsed.get("applicability_domain")
                or "DeepSeek LLM 估算。"
            ),
            "note": "LLM 估算，不计入 trained_model 层。",
        }
    except Exception as exc:
        return {
            "available": False,
            "method": f"deepseek_chat_completion:{model}",
            "reason": f"DeepSeek 调用失败。错误类型：{type(exc).__name__}",
            "applicability_domain": "无可用 LLM 估算。",
        }


def score_route_feasibility(route: Route) -> RouteFeasibility:
    if not route.steps:
        return RouteFeasibility(route.id, 0.0, 0.0, ["路线没有反应步骤"], "无法评分。")

    overall_fraction = 1.0
    risk_flags: list[str] = []
    for step in route.steps:
        estimate = estimate_reaction_yield(step.reaction_smiles, step.template)
        overall_fraction *= estimate.heuristic_yield_percent / 100
        if estimate.confidence == "低":
            risk_flags.append(f"{step.id}: 反应类型置信度低")

    stock_bonus = route.stock_count / max(route.precursor_count, 1)
    step_penalty = 1 / route.depth
    feasibility_score = 0.55 * overall_fraction + 0.30 * stock_bonus + 0.15 * step_penalty

    return RouteFeasibility(
        route_id=route.id,
        heuristic_overall_yield_percent=round(overall_fraction * 100, 1),
        heuristic_feasibility_score=round(feasibility_score, 3),
        risk_flags=risk_flags,
        note="规则可行性评分综合了规则估计产率、叶子前体可购买性和路线步数。",
    )


def check_feasibility_with_deepseek(
    reaction_smiles: str,
    template: str | None = None,
    yield_estimate: YieldEstimate | None = None,
) -> dict[str, object]:
    api_key = _deepseek_api_key()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    estimate = yield_estimate or estimate_reaction_yield(reaction_smiles, template)

    if not api_key:
        return {
            "available": False,
            "method": "deepseek_chat_completion",
            "reason": "DEEPSEEK_API_KEY 未配置。",
            "feasibility": {
                "feasible": True,
                "feasibility_score": estimate.heuristic_yield_percent / 100,
                "confidence": estimate.confidence,
                "risks": estimate.factors,
                "recommendations": [],
            },
        }

    prompt = {
        "reaction_smiles": reaction_smiles,
        "template": template,
        "heuristic_yield_percent": estimate.heuristic_yield_percent,
        "heuristic_confidence": estimate.confidence,
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
                            "你是有机合成化学专家。请基于给定 reaction SMILES 和启发式基线，"
                            "评估该反应在实际实验室条件下的可行性。考虑反应热力学、动力学、"
                            "官能团兼容性、副反应可能性和典型实验条件。只输出 JSON，不输出 Markdown。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请评估该反应的可行性并输出 JSON："
                            "feasible(布尔值), feasibility_score(0-1浮点数), confidence(低/中/高字符串), "
                            "risks(字符串数组, 列出潜在风险), "
                            "recommendations(字符串数组, 给出改进建议)。输入如下：\n"
                            f"{json.dumps(prompt, ensure_ascii=False)}"
                        ),
                    },
                ],
                "temperature": 0.2,
                "max_tokens": 900,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        content = str(payload["choices"][0]["message"]["content"])
        parsed = _parse_llm_json(content)
        confidence = str(parsed.get("confidence") or estimate.confidence)
        if confidence not in {"低", "中", "高"}:
            confidence = estimate.confidence
        return {
            "available": True,
            "method": f"deepseek_chat_completion:{model}",
            "feasibility": {
                "feasible": bool(parsed.get("feasible", True)),
                "feasibility_score": _clamp_float(parsed.get("feasibility_score"), 0.0, 1.0, estimate.heuristic_yield_percent / 100),
                "confidence": confidence,
                "risks": _string_list(parsed.get("risks")),
                "recommendations": _string_list(parsed.get("recommendations")),
            },
        }
    except Exception as exc:
        return {
            "available": False,
            "method": f"deepseek_chat_completion:{model}",
            "reason": f"DeepSeek 调用失败。错误类型：{type(exc).__name__}",
            "feasibility": {
                "feasible": True,
                "feasibility_score": estimate.heuristic_yield_percent / 100,
                "confidence": estimate.confidence,
                "risks": estimate.factors,
                "recommendations": [],
            },
        }


def _deepseek_api_key() -> str | None:
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key
    return _read_env_file_value("DEEPSEEK_API_KEY")


def _read_env_file_value(name: str) -> str | None:
    root = Path(__file__).resolve().parents[1]
    for filename in (".env.local", ".env"):
        path = root / filename
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("\"'")
    return None


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _clamp_float(value: object, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
