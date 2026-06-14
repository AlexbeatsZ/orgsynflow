from core.gaussian import generate_gaussian_input, parse_gaussian_log


def test_generate_gaussian_input_contains_route_and_title() -> None:
    gjf = generate_gaussian_input(
        smiles="CCO",
        title="ethanol opt",
        method="B3LYP",
        basis="6-31G(d)",
        job_type="opt freq",
    )

    assert "%nprocshared=4" in gjf
    assert "# opt freq B3LYP/6-31G(d)" in gjf
    assert "ethanol opt" in gjf
    assert "0 1" in gjf
    assert " TV " not in gjf
    assert "C " in gjf
    assert "O " in gjf


def test_parse_gaussian_log_extracts_key_fields() -> None:
    log = """
 SCF Done:  E(RB3LYP) =  -228.123456789     A.U. after   10 cycles
 Alpha  occ. eigenvalues -- -0.40123 -0.25000
 Alpha virt. eigenvalues --  0.03100  0.10000
 Frequencies --  -521.40   120.00   340.50
 Sum of electronic and thermal Free Energies=        -228.012345
 Normal termination of Gaussian 16
"""

    result = parse_gaussian_log(log)

    assert result.normal_termination is True
    assert result.final_energy_hartree == -228.123456789
    assert result.gibbs_free_energy_hartree == -228.012345
    assert result.imaginary_frequency_count == 1
    assert result.homo_ev is not None
    assert result.lumo_ev is not None
