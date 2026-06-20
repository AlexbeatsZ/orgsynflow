from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adapters.opera_adapter import predict_with_opera
from core.molecule import summarize_molecule


@dataclass(frozen=True)
class PropertyPrediction:
    rdkit: dict[str, Any]
    opera: dict[str, Any] | None
    source: str
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "rdkit": self.rdkit,
            "opera": self.opera,
            "note": self.note,
        }


@dataclass(frozen=True)
class DescriptorSet:
    source: str
    descriptors: dict[str, Any]
    unavailable: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "descriptors": self.descriptors,
            "unavailable": self.unavailable,
        }


def predict_properties(smiles: str, include_opera: bool = False) -> PropertyPrediction:
    rdkit_summary = summarize_molecule(smiles).as_display_dict()
    opera = predict_with_opera(smiles).as_dict() if include_opera else None
    return PropertyPrediction(
        rdkit=rdkit_summary,
        opera=opera,
        source="rdkit+optional-opera",
        note="RDKit 结构描述符；OPERA 可选 QSAR 预测。",
    )


def calculate_descriptors(smiles: str, include_mordred: bool = True) -> DescriptorSet:
    summary = summarize_molecule(smiles)
    descriptors: dict[str, Any] = {
        "canonical_smiles": summary.canonical_smiles,
        "formula": summary.formula,
        "molecular_weight": summary.molecular_weight,
        "logp": summary.logp,
        "tpsa": summary.tpsa,
        "hbd": summary.hbd,
        "hba": summary.hba,
        "rotatable_bonds": summary.rotatable_bonds,
        "ring_count": summary.ring_count,
        "aromatic_ring_count": summary.aromatic_ring_count,
    }
    unavailable: list[str] = []

    if include_mordred:
        try:
            from mordred import Calculator, descriptors as mordred_descriptors
            from rdkit import Chem
        except Exception:
            unavailable.append("mordred")
        else:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                unavailable.append("mordred: invalid SMILES")
            else:
                calc = Calculator(mordred_descriptors, ignore_3D=True)
                values = calc(mol).asdict()
                for key, value in values.items():
                    if len(descriptors) >= 80:
                        break
                    if _is_json_scalar(value):
                        descriptors[f"mordred:{key}"] = value

    return DescriptorSet(
        source="rdkit+mordred_optional",
        descriptors=descriptors,
        unavailable=unavailable,
    )


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)
