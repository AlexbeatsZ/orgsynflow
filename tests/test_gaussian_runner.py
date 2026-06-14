import subprocess
from pathlib import Path

from core.gaussian_runner import run_gaussian_job


def test_run_gaussian_job_invokes_executable_and_parses_log(tmp_path, monkeypatch) -> None:
    def fake_run(command, check, capture_output, text, timeout, cwd):
        log_path = Path(cwd) / "job.log"
        log_path.write_text(
            """
 SCF Done:  E(RB3LYP) =  -1.000000     A.U. after   1 cycles
 Sum of electronic and thermal Free Energies=        -0.990000
 Frequencies --  100.00   200.00   300.00
 Normal termination of Gaussian 16
""",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_gaussian_job("%chk=x.chk\n# opt B3LYP/6-31G(d)\n\nx\n\n0 1\n", tmp_path, executable="fake-g16")

    assert result.success is True
    assert result.log_path is not None
    assert result.parsed_result is not None
    assert result.parsed_result.normal_termination is True
