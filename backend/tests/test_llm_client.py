"""Tests du client LLM.

Les tests marqués `reseau` consomment du quota Gemini : ils sont exclus par
défaut (voir pyproject.toml) et se lancent explicitement avec
`pytest -m reseau` — typiquement une fois au début du hackathon pour valider
la clé, puis avant la démo.
"""

from types import SimpleNamespace

import pytest
from src.config import config
from src.llm_client import LLMError, llm_call, llm_call_with_tools, set_log_llm_call
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


# --- Hook d'observabilité (OBS-6) --------------------------------------------
# `_appeler_avec_reprise` est simulé : ces tests vérifient que le hook est
# appelé avec les bonnes données, sans consommer de quota.


def _fausse_reponse(text="", parsed=None, candidates=None, prompt_tokens=10, sortie_tokens=5):
    return SimpleNamespace(
        text=text,
        parsed=parsed,
        candidates=candidates or [],
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens, candidates_token_count=sortie_tokens
        ),
    )


@pytest.fixture
def hook_capture(monkeypatch):
    appels = []
    set_log_llm_call(lambda **kwargs: appels.append(kwargs))
    yield appels
    set_log_llm_call(None)


def test_llm_call_declenche_le_hook_avec_les_tokens(monkeypatch, hook_capture):
    monkeypatch.setattr(
        "src.llm_client._appeler_avec_reprise",
        lambda *a, **k: _fausse_reponse(text="Bonjour."),
    )
    llm_call("systeme", "utilisateur", etape="classification", trace_id="t1")

    assert len(hook_capture) == 1
    appel = hook_capture[0]
    assert appel["etape"] == "classification"
    assert appel["trace_id"] == "t1"
    assert appel["tokens_entree"] == 10
    assert appel["tokens_sortie"] == 5
    assert appel["reponse_texte"] == "Bonjour."
    assert appel["latence_ms"] >= 0


def test_llm_call_sans_hook_branche_ne_leve_rien(monkeypatch):
    """Le hook n'est branché qu'au démarrage de l'API (lifespan) : un appel
    hors de ce contexte (les autres tests de ce fichier, par exemple) ne doit
    pas planter faute de logger configuré."""
    set_log_llm_call(None)
    monkeypatch.setattr(
        "src.llm_client._appeler_avec_reprise",
        lambda *a, **k: _fausse_reponse(text="ok"),
    )
    assert llm_call("systeme", "utilisateur") == "ok"


def test_llm_call_with_tools_journalise_les_appels_de_fonction(monkeypatch, hook_capture):
    from google.genai import types

    appel_fn = types.FunctionCall(name="verifier_etat_service", args={"service": "reseau"})
    reponse = _fausse_reponse(
        text="",
        candidates=[
            SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(function_call=appel_fn)]))
        ],
    )
    monkeypatch.setattr("src.llm_client._appeler_avec_reprise", lambda *a, **k: reponse)

    llm_call_with_tools([], "systeme", [], etape="agent")

    assert hook_capture[0]["etape"] == "agent"
    assert "verifier_etat_service" in hook_capture[0]["reponse_texte"]


def test_hook_qui_leve_une_exception_n_interrompt_pas_l_appel(monkeypatch):
    """Un bug dans le logger (OBS-6) ne doit jamais faire échouer le
    traitement d'un ticket : c'est un effet de bord, pas une dépendance dure."""

    def hook_casse(**kwargs):
        raise RuntimeError("logger cassé")

    set_log_llm_call(hook_casse)
    monkeypatch.setattr(
        "src.llm_client._appeler_avec_reprise",
        lambda *a, **k: _fausse_reponse(text="ok"),
    )
    try:
        assert llm_call("systeme", "utilisateur") == "ok"
    finally:
        set_log_llm_call(None)


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
