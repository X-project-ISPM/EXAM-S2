"""Tests du client LLM.

Les tests marqués `reseau` consomment du quota Gemini : ils sont exclus par
défaut (voir pyproject.toml) et se lancent explicitement avec
`pytest -m reseau` — typiquement une fois au début du hackathon pour valider
la clé, puis avant la démo.
"""

import pytest

from src.config import config
from src.llm_client import LLMError, llm_call
from src.schemas import Classification


def test_erreur_explicite_sans_cle(monkeypatch):
    """Sans clé, l'échec doit être lisible et actionnable, pas un stacktrace
    obscur du SDK au milieu de la démo."""
    from src import llm_client

    llm_client._get_client.cache_clear()
    monkeypatch.setattr(config, "gemini_api_key", "")

    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        llm_call("systeme", "utilisateur")

    llm_client._get_client.cache_clear()


@pytest.mark.reseau
def test_appel_texte_reel():
    reponse = llm_call("Tu réponds en un seul mot.", "Dis bonjour.")
    assert isinstance(reponse, str)
    assert reponse.strip()


@pytest.mark.reseau
def test_sortie_structuree_reelle():
    """Vérifie le chemin critique : le modèle rend bien un objet Pydantic
    validé, pas du texte à parser à la main."""
    resultat = llm_call(
        "Tu classifies des tickets de support informatique.",
        "Impossible d'accéder au serveur, toute l'équipe est bloquée.",
        response_schema=Classification,
    )
    assert isinstance(resultat, Classification)
    assert resultat.categorie in Classification.model_fields["categorie"].annotation.__args__
    assert resultat.priorite in {"basse", "moyenne", "haute", "critique"}
