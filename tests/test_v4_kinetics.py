from core.gaussian import GaussianResult
from core.kinetics import analyze_energy_profile, eyring_rate_constant


def test_eyring_rate_constant_decreases_with_barrier() -> None:
    fast = eyring_rate_constant(50.0, temperature_k=298.15)
    slow = eyring_rate_constant(80.0, temperature_k=298.15)

    assert fast > slow
    assert fast > 0


def test_energy_profile_computes_barrier_and_ts_validity() -> None:
    reactant = GaussianResult(True, -100.0, -100.0, 0, None, None, [])
    product = GaussianResult(True, -100.02, -100.02, 0, None, None, [])
    ts = GaussianResult(True, -99.97, -99.97, 1, None, None, [])

    profile = analyze_energy_profile(reactant, product, ts)

    assert profile.delta_g_rxn_kj_mol < 0
    assert profile.delta_g_activation_kj_mol > 0
    assert profile.ts_is_plausible is True
    assert profile.rate_constant_s_inv > 0
