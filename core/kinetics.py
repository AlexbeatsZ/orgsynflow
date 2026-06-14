from __future__ import annotations

import math
from dataclasses import dataclass

from core.gaussian import GaussianResult


HARTREE_TO_KJ_MOL = 2625.499638
R_KJ_MOL_K = 0.00831446261815324
K_B = 1.380649e-23
H = 6.62607015e-34


@dataclass(frozen=True)
class EnergyProfile:
    delta_g_rxn_kj_mol: float | None
    delta_g_activation_kj_mol: float | None
    rate_constant_s_inv: float | None
    ts_is_plausible: bool
    verdict: str

    def as_dict(self) -> dict[str, object]:
        return {
            "delta_g_rxn_kj_mol": self.delta_g_rxn_kj_mol,
            "delta_g_activation_kj_mol": self.delta_g_activation_kj_mol,
            "rate_constant_s_inv": self.rate_constant_s_inv,
            "ts_is_plausible": self.ts_is_plausible,
            "verdict": self.verdict,
        }


def eyring_rate_constant(delta_g_activation_kj_mol: float, temperature_k: float = 298.15) -> float:
    exponent = -delta_g_activation_kj_mol / (R_KJ_MOL_K * temperature_k)
    return (K_B * temperature_k / H) * math.exp(exponent)


def analyze_energy_profile(
    reactants: GaussianResult,
    products: GaussianResult,
    transition_state: GaussianResult,
    temperature_k: float = 298.15,
) -> EnergyProfile:
    if (
        reactants.gibbs_free_energy_hartree is None
        or products.gibbs_free_energy_hartree is None
        or transition_state.gibbs_free_energy_hartree is None
    ):
        return EnergyProfile(
            delta_g_rxn_kj_mol=None,
            delta_g_activation_kj_mol=None,
            rate_constant_s_inv=None,
            ts_is_plausible=False,
            verdict="缺少 Gibbs 自由能，无法计算反应能垒。",
        )

    delta_rxn = (
        products.gibbs_free_energy_hartree - reactants.gibbs_free_energy_hartree
    ) * HARTREE_TO_KJ_MOL
    delta_act = (
        transition_state.gibbs_free_energy_hartree - reactants.gibbs_free_energy_hartree
    ) * HARTREE_TO_KJ_MOL
    ts_ok = transition_state.normal_termination and transition_state.imaginary_frequency_count == 1
    rate = eyring_rate_constant(delta_act, temperature_k) if delta_act >= 0 else None

    if not ts_ok:
        verdict = "TS 结果不满足一个虚频的基本判据，需人工复核。"
    elif delta_act < 0:
        verdict = "TS 自由能低于反应物，能垒数据不合理。"
    elif delta_act < 60:
        verdict = "能垒较低，常温下可能较快。"
    elif delta_act < 100:
        verdict = "能垒中等，反应可能需要加热或催化。"
    else:
        verdict = "能垒偏高，路线动力学风险较大。"

    return EnergyProfile(
        delta_g_rxn_kj_mol=round(delta_rxn, 3),
        delta_g_activation_kj_mol=round(delta_act, 3),
        rate_constant_s_inv=rate,
        ts_is_plausible=ts_ok,
        verdict=verdict,
    )
