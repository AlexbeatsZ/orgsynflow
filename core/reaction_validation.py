from __future__ import annotations

from collections import Counter
from typing import Any

from core.molecule import rdkit_modules
from core.reaction_explain import explain_reaction
from core.yield_predictor import estimate_reaction_yield_layered


def validate_reaction_smiles(reaction_smiles: str, template: str | None = None) -> dict[str, Any]:
    cleaned = reaction_smiles.strip()
    errors: list[str] = []
    warnings: list[str] = []

    if ">>" not in cleaned:
        errors.append("Reaction SMILES must contain '>>'.")
        return _result(cleaned, False, errors, warnings, {}, template)

    reactants_text, products_text = cleaned.split(">>", 1)
    reactants = [item for item in reactants_text.split(".") if item]
    products = [item for item in products_text.split(".") if item]
    if not reactants:
        errors.append("Reaction must contain at least one reactant.")
    if not products:
        errors.append("Reaction must contain at least one product.")

    modules = rdkit_modules()
    element_balance: dict[str, Any] = {"available": False}
    if modules:
        Chem = modules[0]
        reactant_counts = Counter()
        product_counts = Counter()
        for side_name, molecules, counts in (
            ("reactant", reactants, reactant_counts),
            ("product", products, product_counts),
        ):
            for smiles in molecules:
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    errors.append(f"Invalid {side_name} SMILES: {smiles}")
                    continue
                counts.update(atom.GetSymbol() for atom in mol.GetAtoms())
        if not errors:
            delta = {
                symbol: product_counts[symbol] - reactant_counts[symbol]
                for symbol in sorted(set(reactant_counts) | set(product_counts))
                if product_counts[symbol] != reactant_counts[symbol]
            }
            element_balance = {
                "available": True,
                "reactants": dict(reactant_counts),
                "products": dict(product_counts),
                "delta": delta,
                "balanced": not delta,
            }
            if delta:
                warnings.append("Element counts are not balanced; check missing reagents, salts, or byproducts.")
    else:
        warnings.append("RDKit is unavailable; structure validation and element balance were skipped.")

    valid = not errors
    return _result(cleaned, valid, errors, warnings, element_balance, template)


def _result(
    reaction_smiles: str,
    valid: bool,
    errors: list[str],
    warnings: list[str],
    element_balance: dict[str, Any],
    template: str | None,
) -> dict[str, Any]:
    explanation = explain_reaction(reaction_smiles, template).as_dict()
    feasibility = estimate_reaction_yield_layered(reaction_smiles, template)
    return {
        "reaction_smiles": reaction_smiles,
        "valid": valid,
        "status": "valid" if valid else "invalid",
        "errors": errors,
        "warnings": warnings,
        "element_balance": element_balance,
        "explanation": explanation,
        "feasibility": feasibility,
    }
