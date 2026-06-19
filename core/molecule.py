from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import html
import re
from typing import Any


@dataclass(frozen=True)
class MoleculeSummary:
    smiles: str
    valid: bool
    canonical_smiles: str | None
    formula: str | None
    molecular_weight: float | None
    logp: float | None
    tpsa: float | None
    hbd: int | None
    hba: int | None
    rotatable_bonds: int | None
    ring_count: int | None
    aromatic_ring_count: int | None
    warning: str | None = None

    def as_display_dict(self) -> dict[str, Any]:
        return {
            "SMILES": self.smiles,
            "Canonical SMILES": self.canonical_smiles or "-",
            "Formula": self.formula or "-",
            "MW": _round_or_dash(self.molecular_weight),
            "LogP": _round_or_dash(self.logp),
            "TPSA": _round_or_dash(self.tpsa),
            "HBD": self.hbd if self.hbd is not None else "-",
            "HBA": self.hba if self.hba is not None else "-",
            "Rotatable bonds": self.rotatable_bonds if self.rotatable_bonds is not None else "-",
            "Ring count": self.ring_count if self.ring_count is not None else "-",
            "Aromatic rings": self.aromatic_ring_count if self.aromatic_ring_count is not None else "-",
        }


def _round_or_dash(value: float | None) -> float | str:
    return round(value, 3) if value is not None else "-"


@lru_cache(maxsize=1)
def rdkit_modules() -> tuple[Any, Any, Any, Any] | None:
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

        return Chem, Crippen, Descriptors, Lipinski, rdMolDescriptors
    except Exception:
        return None


def has_rdkit() -> bool:
    return rdkit_modules() is not None


def summarize_molecule(smiles: str) -> MoleculeSummary:
    modules = rdkit_modules()
    cleaned = smiles.strip()
    if not modules:
        return MoleculeSummary(
            smiles=cleaned,
            valid=False,
            canonical_smiles=None,
            formula=None,
            molecular_weight=None,
            logp=None,
            tpsa=None,
            hbd=None,
            hba=None,
            rotatable_bonds=None,
            ring_count=None,
            aromatic_ring_count=None,
            warning="RDKit is not installed. Run `uv sync --extra chem` for structure validation and descriptors.",
        )

    Chem, Crippen, Descriptors, Lipinski, rdMolDescriptors = modules
    mol = Chem.MolFromSmiles(cleaned)
    if mol is None:
        return MoleculeSummary(
            smiles=cleaned,
            valid=False,
            canonical_smiles=None,
            formula=None,
            molecular_weight=None,
            logp=None,
            tpsa=None,
            hbd=None,
            hba=None,
            rotatable_bonds=None,
            ring_count=None,
            aromatic_ring_count=None,
            warning="RDKit could not parse this SMILES.",
        )

    return MoleculeSummary(
        smiles=cleaned,
        valid=True,
        canonical_smiles=Chem.MolToSmiles(mol),
        formula=rdMolDescriptors.CalcMolFormula(mol),
        molecular_weight=Descriptors.MolWt(mol),
        logp=Crippen.MolLogP(mol),
        tpsa=rdMolDescriptors.CalcTPSA(mol),
        hbd=Lipinski.NumHDonors(mol),
        hba=Lipinski.NumHAcceptors(mol),
        rotatable_bonds=Lipinski.NumRotatableBonds(mol),
        ring_count=rdMolDescriptors.CalcNumRings(mol),
        aromatic_ring_count=rdMolDescriptors.CalcNumAromaticRings(mol),
    )


def molecule_svg(smiles: str, size: tuple[int, int] = (320, 220)) -> str | None:
    modules = rdkit_modules()
    if not modules:
        return formula_svg(smiles, size=size)

    Chem = modules[0]
    try:
        from rdkit.Chem.Draw import rdMolDraw2D
    except Exception:
        return formula_svg(smiles, size=size)

    cleaned = smiles.strip()
    mol = Chem.MolFromSmiles(cleaned)
    if mol is None:
        return formula_svg(cleaned, size=size)

    drawer = rdMolDraw2D.MolDraw2DSVG(*size)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


_FORMULA_COMPONENT_RE = re.compile(r"^(?:\d+)?(?:[A-Z][a-z]?\d*)+$")


def formula_svg(formula: str, size: tuple[int, int] = (320, 220)) -> str | None:
    cleaned = formula.strip()
    if not _is_formula_like(cleaned):
        return None

    width, height = size
    font_size = max(18, min(34, int(width / max(len(cleaned) * 0.55, 5))))
    subscript_size = max(12, int(font_size * 0.62))
    tspans = "".join(_formula_tspans(cleaned, subscript_size))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="{width / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="Inter, Segoe UI, Arial, sans-serif" '
        f'font-size="{font_size}" font-weight="650" fill="#17202a">{tspans}</text>'
        f'<text x="{width / 2:.1f}" y="{height - 24}" text-anchor="middle" '
        'font-family="Cascadia Mono, Consolas, monospace" font-size="12" fill="#64748b">'
        'formula notation'
        "</text>"
        "</svg>"
    )


def _is_formula_like(value: str) -> bool:
    parts = re.split(r"[.·•]", value)
    return bool(parts) and all(_FORMULA_COMPONENT_RE.fullmatch(part) for part in parts)


def _formula_tspans(value: str, subscript_size: int) -> list[str]:
    spans: list[str] = []
    previous_was_element = False
    index = 0
    while index < len(value):
        char = value[index]
        if char in ".·•":
            spans.append('<tspan dx="6">&#183;</tspan><tspan dx="6"></tspan>')
            previous_was_element = False
            index += 1
            continue

        if char.isdigit():
            start = index
            while index < len(value) and value[index].isdigit():
                index += 1
            digits = html.escape(value[start:index])
            if previous_was_element:
                spans.append(
                    f'<tspan baseline-shift="sub" font-size="{subscript_size}">{digits}</tspan>'
                )
            else:
                spans.append(f"<tspan>{digits}</tspan>")
            previous_was_element = False
            continue

        start = index
        index += 1
        if index < len(value) and value[index].islower():
            index += 1
        spans.append(f"<tspan>{html.escape(value[start:index])}</tspan>")
        previous_was_element = True
    return spans
