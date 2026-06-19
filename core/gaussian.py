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

    def as_dict(self) -> dict[str, object]:
        return {
            "normal_termination": self.normal_termination,
            "final_energy_hartree": self.final_energy_hartree,
            "gibbs_free_energy_hartree": self.gibbs_free_energy_hartree,
            "imaginary_frequency_count": self.imaginary_frequency_count,
            "homo_ev": self.homo_ev,
            "lumo_ev": self.lumo_ev,
            "warnings": self.warnings,
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
    )


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
