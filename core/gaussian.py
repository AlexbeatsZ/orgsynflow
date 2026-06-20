from __future__ import annotations

import re
from dataclasses import dataclass


HARTREE_TO_EV = 27.211386245988


@dataclass(frozen=True)
class GaussianResult:
    normal_termination: bool
    final_energy_hartree: float | None
    gibbs_free_energy_hartree: float | None
    imaginary_frequency_count: int
    homo_ev: float | None
    lumo_ev: float | None
    warnings: list[str]
    optimization_steps: list[dict[str, object]] | None = None
    frequencies_cm1: list[float] | None = None
    vibration_modes: list[dict[str, object]] | None = None
    final_coordinates_xyz: str | None = None
    scf_cycles: list[dict[str, object]] | None = None
    convergence_tables: list[dict[str, object]] | None = None
    log_issues: dict[str, list[dict[str, object]]] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "normal_termination": self.normal_termination,
            "final_energy_hartree": self.final_energy_hartree,
            "gibbs_free_energy_hartree": self.gibbs_free_energy_hartree,
            "imaginary_frequency_count": self.imaginary_frequency_count,
            "homo_ev": self.homo_ev,
            "lumo_ev": self.lumo_ev,
            "warnings": self.warnings,
            "optimization_steps": self.optimization_steps,
            "frequencies_cm1": self.frequencies_cm1,
            "vibration_modes": self.vibration_modes,
            "final_coordinates_xyz": self.final_coordinates_xyz,
            "scf_cycles": self.scf_cycles,
            "convergence_tables": self.convergence_tables,
            "log_issues": self.log_issues,
        }


def generate_gaussian_input(
    smiles: str,
    title: str,
    method: str = "B3LYP",
    basis: str = "6-31G(d)",
    job_type: str = "opt freq",
    charge: int = 0,
    multiplicity: int = 1,
    nproc: int = 4,
    memory: str = "4GB",
) -> str:
    route = f"# {job_type} {method}/{basis}"
    coordinates = coordinates_from_smiles(smiles)
    return "\n".join(
        [
            f"%nprocshared={nproc}",
            f"%mem={memory}",
            route,
            "",
            title,
            "",
            f"{charge} {multiplicity}",
            coordinates,
            "",
            "",
        ]
    )


def coordinates_from_smiles(smiles: str) -> str:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except Exception as exc:
        raise RuntimeError("生成 Gaussian 输入需要 RDKit 以便从 SMILES 生成 3D 坐标。") from exc

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"无法解析 SMILES：{smiles}")
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 20260614
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise RuntimeError("RDKit 3D 构象生成失败，无法写入 Gaussian 坐标。")
    AllChem.UFFOptimizeMolecule(mol, maxIters=200)
    conformer = mol.GetConformer()
    lines: list[str] = []
    for atom in mol.GetAtoms():
        position = conformer.GetAtomPosition(atom.GetIdx())
        lines.append(
            f"{atom.GetSymbol():<2} {position.x:>12.6f} {position.y:>12.6f} {position.z:>12.6f}"
        )
    return "\n".join(lines)


def _coordinates_from_smiles(smiles: str) -> str:
    return coordinates_from_smiles(smiles)


def parse_gaussian_log(text: str) -> GaussianResult:
    warnings: list[str] = []
    normal = "Normal termination" in text
    final_energy = _last_float(r"SCF Done:\s+E\([^)]+\)\s+=\s+(-?\d+\.\d+)", text)
    gibbs = _last_float(r"Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)", text)
    frequencies = _all_frequency_values(text)
    imaginary_count = sum(1 for value in frequencies if value < 0)
    homo_ev, lumo_ev = _parse_homo_lumo(text)
    progress = parse_gaussian_log_progress(text)

    if final_energy is None:
        warnings.append("未找到 SCF Done 最终能量。")
    if gibbs is None:
        warnings.append("未找到 Gibbs 自由能。")
    if not normal:
        warnings.append("Gaussian 输出未显示 Normal termination。")

    return GaussianResult(
        normal_termination=normal,
        final_energy_hartree=final_energy,
        gibbs_free_energy_hartree=gibbs,
        imaginary_frequency_count=imaginary_count,
        homo_ev=homo_ev,
        lumo_ev=lumo_ev,
        warnings=warnings,
        optimization_steps=progress["optimization_steps"] or None,
        frequencies_cm1=frequencies,
        vibration_modes=_parse_vibration_modes(text),
        final_coordinates_xyz=_parse_final_coordinates_xyz(text),
        scf_cycles=progress["scf_cycles"] or None,
        convergence_tables=progress["convergence_tables"] or None,
        log_issues=progress["issues"],
    )


def parse_gaussian_log_progress(text: str) -> dict[str, object]:
    """Extract live progress from a Gaussian log/out file.

    The shape is intentionally UI-friendly and safe to expose while Gaussian is
    still writing the log. It mirrors the useful parts of the older Gradio
    project: SCF cycles, optimization convergence tables, and warnings/errors.
    """
    scf_cycles = _parse_scf_cycles(text)
    convergence_tables = _parse_convergence_tables(text)
    optimization_steps = _merge_optimization_steps(scf_cycles, convergence_tables)
    issues = _parse_log_issues(text)
    return {
        "scf_cycles": scf_cycles,
        "convergence_tables": convergence_tables,
        "optimization_steps": optimization_steps,
        "issues": issues,
        "summary": _progress_summary(scf_cycles, convergence_tables, issues, text),
    }


def _last_float(pattern: str, text: str) -> float | None:
    matches = re.findall(pattern, text)
    return float(matches[-1]) if matches else None


def _all_frequency_values(text: str) -> list[float]:
    values: list[float] = []
    for line in text.splitlines():
        if "Frequencies --" not in line:
            continue
        values.extend(float(item) for item in re.findall(r"-?\d+\.\d+", line))
    return values


def _parse_scf_cycles(text: str) -> list[dict[str, object]]:
    cycles: list[dict[str, object]] = []
    done_pattern = re.compile(
        r"SCF Done:\s+E\(([^)]+)\)\s+=\s+(-?\d+(?:\.\d+)?(?:[DEde][+-]?\d+)?)\s+A\.U\.\s+after\s+(\d+)\s+cycles"
    )
    for index, match in enumerate(done_pattern.finditer(text), start=1):
        cycles.append({
            "step": index,
            "method": match.group(1),
            "energy_hartree": _gaussian_float(match.group(2)),
            "cycles": int(match.group(3)),
            "in_progress": False,
        })

    current_pattern = re.compile(r"Cycle\s+(\d+)\s+Pass\s+\d+.*?E=\s*(-?\d+(?:\.\d+)?(?:[DEde][+-]?\d+)?)")
    current_matches = list(current_pattern.finditer(text))
    if current_matches:
        current = current_matches[-1]
        current_energy = _gaussian_float(current.group(2))
        if not cycles or cycles[-1].get("energy_hartree") != current_energy:
            cycles.append({
                "step": len(cycles) + 1,
                "method": "In Progress",
                "energy_hartree": current_energy,
                "cycles": int(current.group(1)),
                "in_progress": True,
            })
    return cycles


def _parse_convergence_tables(text: str) -> list[dict[str, object]]:
    pattern = re.compile(
        r"Item\s+Value\s+Threshold\s+Converged\?\s*\n\s*"
        r"Maximum Force\s+(\S+)\s+(\S+)\s+(YES|NO)\s*\n\s*"
        r"RMS\s+Force\s+(\S+)\s+(\S+)\s+(YES|NO)\s*\n\s*"
        r"Maximum Displacement\s+(\S+)\s+(\S+)\s+(YES|NO)\s*\n\s*"
        r"RMS\s+Displacement\s+(\S+)\s+(\S+)\s+(YES|NO)",
        re.IGNORECASE,
    )
    tables: list[dict[str, object]] = []
    names = ("Maximum Force", "RMS Force", "Maximum Displacement", "RMS Displacement")
    for index, match in enumerate(pattern.finditer(text), start=1):
        rows = []
        groups = match.groups()
        for row_index, name in enumerate(names):
            offset = row_index * 3
            rows.append({
                "item": name,
                "value": _safe_float(groups[offset]),
                "threshold": _safe_float(groups[offset + 1]),
                "converged": groups[offset + 2].upper() == "YES",
            })
        tables.append({"step": index, "rows": rows})
    return tables


def _merge_optimization_steps(
    scf_cycles: list[dict[str, object]],
    convergence_tables: list[dict[str, object]],
) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    for index, scf in enumerate(scf_cycles):
        if scf.get("in_progress"):
            continue
        table = convergence_tables[index] if index < len(convergence_tables) else None
        row_by_name = {
            str(row.get("item")): row
            for row in (table.get("rows", []) if isinstance(table, dict) else [])
            if isinstance(row, dict)
        }
        step: dict[str, object] = {
            "step": len(steps) + 1,
            "energy_hartree": scf.get("energy_hartree"),
            "scf_cycles": scf.get("cycles"),
        }
        for source_name, target_name in (
            ("Maximum Force", "max_force"),
            ("RMS Force", "rms_force"),
            ("Maximum Displacement", "max_displacement"),
            ("RMS Displacement", "rms_displacement"),
        ):
            row = row_by_name.get(source_name)
            if row:
                step[target_name] = row.get("value")
                step[f"{target_name}_threshold"] = row.get("threshold")
                step[f"{target_name}_converged"] = row.get("converged")
        steps.append(step)
    return steps


def _parse_log_issues(text: str) -> dict[str, list[dict[str, object]]]:
    warnings: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        lower = line.lower()
        stripped = line.strip()
        if not stripped:
            continue
        if "warning" in lower or "small imaginary frequenc" in lower or "eigenvalue problem" in lower:
            warnings.append({"line": index, "text": stripped})
        if "convergence failure" in lower or "galloc" in lower or "out-of-memory" in lower:
            errors.append({"line": index, "text": stripped})
        if "error termination" in lower or "erroneous write" in lower:
            start = max(0, index - 4)
            context = "\n".join(lines[start:index]).strip()
            errors.append({"line": index, "text": context or stripped})
        elif "error" in lower and "error on total polarization charges" not in lower:
            errors.append({"line": index, "text": stripped})
    return {"warnings": warnings[:50], "errors": errors[:50]}


def _progress_summary(
    scf_cycles: list[dict[str, object]],
    convergence_tables: list[dict[str, object]],
    issues: dict[str, list[dict[str, object]]],
    text: str,
) -> str:
    if "Normal termination" in text:
        return "Gaussian 正常结束。"
    if issues.get("errors"):
        return f"检测到 {len(issues['errors'])} 个错误/异常。"
    if convergence_tables:
        latest = convergence_tables[-1]
        rows = latest.get("rows", []) if isinstance(latest, dict) else []
        converged = sum(1 for row in rows if isinstance(row, dict) and row.get("converged"))
        return f"优化第 {latest.get('step')} 步：{converged}/4 项收敛。"
    if scf_cycles:
        latest = scf_cycles[-1]
        status = "正在进行" if latest.get("in_progress") else "已完成"
        return f"SCF {status}：第 {latest.get('cycles')} 轮，E={latest.get('energy_hartree')} Ha。"
    return "等待 Gaussian 写入 SCF/优化信息。"


def _parse_vibration_modes(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    modes: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if "Frequencies --" not in line:
            index += 1
            continue
        freqs = [float(item) for item in re.findall(r"-?\d+\.\d+", line)]
        if not freqs:
            index += 1
            continue
        displacements: list[list[list[float]]] = [[] for _ in freqs]
        cursor = index + 1
        while cursor < len(lines) and "Atom  AN" not in lines[cursor]:
            if "Frequencies --" in lines[cursor]:
                break
            cursor += 1
        if cursor < len(lines) and "Atom  AN" in lines[cursor]:
            cursor += 1
            while cursor < len(lines):
                parts = lines[cursor].split()
                if len(parts) < 2 + 3 * len(freqs):
                    break
                try:
                    int(parts[0])
                    int(parts[1])
                    values = [float(item) for item in parts[2:2 + 3 * len(freqs)]]
                except ValueError:
                    break
                for mode_index in range(len(freqs)):
                    offset = mode_index * 3
                    displacements[mode_index].append(values[offset:offset + 3])
                cursor += 1
        for freq, mode_displacements in zip(freqs, displacements):
            modes.append({"frequency_cm1": freq, "displacements": mode_displacements})
        index = max(cursor, index + 1)
    return modes


def _parse_final_coordinates_xyz(text: str) -> str | None:
    orientation_pattern = re.compile(
        r"(?:Standard|Input) orientation:\s*\n\s*-+\s*\n"
        r".*?Coordinates \(Angstroms\).*?\n\s*-+\s*\n"
        r"(?P<body>.*?)\n\s*-+",
        re.DOTALL,
    )
    matches = list(orientation_pattern.finditer(text))
    if not matches:
        return None
    atoms: list[str] = []
    for line in matches[-1].group("body").splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            atomic_number = int(parts[1])
            x, y, z = float(parts[3]), float(parts[4]), float(parts[5])
        except ValueError:
            continue
        atoms.append(f"{_element_symbol(atomic_number):<2} {x: .8f} {y: .8f} {z: .8f}")
    if not atoms:
        return None
    return f"{len(atoms)}\nGaussian final coordinates\n" + "\n".join(atoms) + "\n"


def _element_symbol(atomic_number: int) -> str:
    symbols = [
        "", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
        "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
        "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
        "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
        "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
        "Sb", "Te", "I", "Xe",
    ]
    return symbols[atomic_number] if 0 < atomic_number < len(symbols) else str(atomic_number)


def _gaussian_float(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def _safe_float(value: str) -> float | str:
    try:
        return _gaussian_float(value)
    except ValueError:
        return value


def _parse_homo_lumo(text: str) -> tuple[float | None, float | None]:
    occupied: list[float] = []
    virtual: list[float] = []
    for line in text.splitlines():
        if "occ. eigenvalues" in line:
            occupied.extend(float(item) for item in re.findall(r"-?\d+\.\d+", line))
        if "virt. eigenvalues" in line:
            virtual.extend(float(item) for item in re.findall(r"-?\d+\.\d+", line))
    homo = occupied[-1] * HARTREE_TO_EV if occupied else None
    lumo = virtual[0] * HARTREE_TO_EV if virtual else None
    return homo, lumo
