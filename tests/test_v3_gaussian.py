from core.gaussian import generate_gaussian_input, parse_gaussian_log, parse_gaussian_log_progress


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


def test_parse_gaussian_log_progress_extracts_scf_and_convergence_table() -> None:
    log = """
 SCF Done:  E(RB3LYP) =  -228.100000000     A.U. after   8 cycles
         Item               Value     Threshold  Converged?
 Maximum Force            0.000012     0.000450     YES
 RMS     Force            0.000004     0.000300     YES
 Maximum Displacement     0.001200     0.001800     YES
 RMS     Displacement     0.000700     0.001200     YES
 SCF Done:  E(RB3LYP) =  -228.123456789     A.U. after   10 cycles
         Item               Value     Threshold  Converged?
 Maximum Force            0.000010     0.000450     YES
 RMS     Force            0.000003     0.000300     YES
 Maximum Displacement     0.001000     0.001800     YES
 RMS     Displacement     0.000600     0.001200     YES
 Normal termination of Gaussian 16
"""

    progress = parse_gaussian_log_progress(log)

    assert progress["summary"] == "Gaussian 正常结束。"
    assert len(progress["scf_cycles"]) == 2
    assert len(progress["convergence_tables"]) == 2
    assert progress["optimization_steps"][-1]["max_force"] == 0.00001
