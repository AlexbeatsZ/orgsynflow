from __future__ import annotations

from dataclasses import dataclass

from core.reaction_mapping import map_reaction


@dataclass(frozen=True)
class TransitionStatePlan:
    reaction_smiles: str
    status: str
    validation_level: str
    gaussian_scan_route: str
    gaussian_ts_route: str
    gaussian_irc_route: str
    reaction_mapping: dict[str, object]
    suggested_steps: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, object]:
        return {
            "reaction_smiles": self.reaction_smiles,
            "status": self.status,
            "validation_level": self.validation_level,
            "gaussian_scan_route": self.gaussian_scan_route,
            "gaussian_ts_route": self.gaussian_ts_route,
            "gaussian_irc_route": self.gaussian_irc_route,
            "reaction_mapping": self.reaction_mapping,
            "suggested_steps": self.suggested_steps,
            "warnings": self.warnings,
        }


def plan_transition_state_search(reaction_smiles: str) -> TransitionStatePlan:
    mapping = map_reaction(reaction_smiles)
    warnings = [
        "该结果是 TS 搜索计划，不是已验证过渡态。",
        "必须通过 Opt=TS + freq 一个虚频 + IRC 连接性检查后才能用于动力学结论。",
    ]
    if mapping.status != "mapped":
        warnings.append("缺少可靠原子映射；scan 坐标需要人工检查。")

    return TransitionStatePlan(
        reaction_smiles=reaction_smiles,
        status="planned",
        validation_level="未验证",
        gaussian_scan_route="# opt=modredundant freq B3LYP/6-31G(d)",
        gaussian_ts_route="# opt=(ts,calcfc,noeigentest) freq B3LYP/6-31G(d)",
        gaussian_irc_route="# irc=(calcfc,forward,reverse) B3LYP/6-31G(d)",
        reaction_mapping=mapping.as_dict(),
        suggested_steps=[
            "用 RDKit/CREST 为反应物、产物和猜测 TS 准备合理构象。",
            "根据反应中心选择形成键或断裂键作为 relaxed scan 坐标。",
            "从 scan 峰值附近结构启动 Gaussian Opt=TS。",
            "freq 检查必须只有一个虚频，并确认虚频模式沿反应坐标。",
            "运行 IRC，确认 TS 两侧连接到目标反应物和产物。",
        ],
        warnings=warnings,
    )
