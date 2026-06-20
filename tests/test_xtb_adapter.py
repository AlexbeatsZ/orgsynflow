from __future__ import annotations

import subprocess
import threading

from adapters import xtb_adapter


class _FakeStdin:
    def __init__(self) -> None:
        self.value = ""

    def write(self, value: str) -> None:
        self.value += value

    def close(self) -> None:
        pass


class _FakeProcess:
    def __init__(self, command: list[str], **_: object) -> None:
        self.command = command
        self.returncode = 0
        self.stdin = _FakeStdin()

    def communicate(self, input: str | None = None, timeout: float | None = None) -> tuple[str, str]:
        if input:
            self.stdin.write(input)
        return (
            "TOTAL ENERGY -5.0\n"
            "__ORGSYNFLOW_CREST_BEST_XYZ_BEGIN__\n"
            "2\nlowest conformer\nH 0 0 0\nH 0 0 1\n"
            "__ORGSYNFLOW_CREST_BEST_XYZ_END__\n",
            "",
        )

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


def test_wsl_crest_runs_inside_unique_workdir_and_returns_lowest_conformer(monkeypatch) -> None:
    processes: list[_FakeProcess] = []

    def fake_popen(command: list[str], **kwargs: object) -> _FakeProcess:
        process = _FakeProcess(command, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(xtb_adapter.subprocess, "Popen", fake_popen)

    first = xtb_adapter._run_wsl("/opt/crest", "2\n\nH 0 0 0\nH 0 0 1\n", "crest_jobs", "CREST", 30)
    second = xtb_adapter._run_wsl("/opt/crest", "2\n\nH 0 0 0\nH 0 0 1\n", "crest_jobs", "CREST", 30)

    script = processes[0].command[-1]
    assert processes[0].command[:5] == ["wsl", "-e", "setsid", "--wait", "bash"]
    assert 'cd "$work_dir"' in script
    assert first.work_dir != second.work_dir
    assert first.data["lowest_conformer_xyz"].startswith("2\nlowest conformer")


def test_wsl_crest_honours_preexisting_cancel_request(monkeypatch) -> None:
    processes: list[_FakeProcess] = []

    def fake_popen(command: list[str], **kwargs: object) -> _FakeProcess:
        process = _FakeProcess(command, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(xtb_adapter.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    cancel_event = threading.Event()
    cancel_event.set()

    result = xtb_adapter._run_wsl("/opt/crest", "0\n\n", "crest_jobs", "CREST", 30, cancel_event)

    assert result.status == "cancelled"


def test_local_failure_uses_process_output_as_reason(monkeypatch, tmp_path) -> None:
    def fake_popen(command: list[str], **kwargs: object) -> _FakeProcess:
        process = _FakeProcess(command, **kwargs)
        process.returncode = 1
        process.communicate = lambda input=None, timeout=None: ("local failure", "")
        return process

    monkeypatch.setattr(xtb_adapter.subprocess, "Popen", fake_popen)

    result = xtb_adapter._run(["crest", "input.xyz"], tmp_path, "CREST", 30)

    assert result.status == "failed"
    assert result.reason == "local failure"
