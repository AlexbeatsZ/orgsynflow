from core.reaction_explain import explain_reaction


def test_explain_acetylation_reaction_in_chinese() -> None:
    explanation = explain_reaction(
        "O=C(O)c1ccccc1O.CC(=O)OC(C)=O>>CC(=O)Oc1ccccc1C(=O)O",
        template="Phenol acetylation",
    )

    assert explanation.reaction_type == "酰化/乙酰化"
    assert "C-O" in explanation.formed_bonds
    assert "亲核取代" in explanation.summary


def test_explain_ester_hydrolysis_reaction() -> None:
    explanation = explain_reaction(
        "COC(=O)c1ccccc1O>>O=C(O)c1ccccc1O",
        template="Ester hydrolysis",
    )

    assert explanation.reaction_type == "酯水解"
    assert "C-O" in explanation.broken_bonds
    assert "羧酸" in explanation.summary
