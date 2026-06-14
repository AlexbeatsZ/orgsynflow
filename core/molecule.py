from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
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
        return None

    Chem = modules[0]
    try:
        from rdkit.Chem.Draw import rdMolDraw2D
    except Exception:
        return None

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    drawer = rdMolDraw2D.MolDraw2DSVG(*size)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()

