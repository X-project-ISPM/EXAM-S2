"""Tests de l'observabilité (OBS-1, OBS-3, OBS-4, OBS-6).

Chaque test redirige `config.dossier_logs` vers un répertoire temporaire
(`tmp_path`) : les journaux JSONL réels de `logs/` ne sont jamais touchés par
la suite de tests.
"""

from types import SimpleNamespace

import pytest
from src.config import config
from src.observability import (
    ChronoLatence,
    estimer_cout,
    lire_dernieres_traces,
    lire_derniers_appels_llm,
    lire_derniers_appels_outils,
    log_llm_call,
    log_tool_call,
    log_trace,
)


@pytest.fixture(autouse=True)
def _logs_isoles(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "dossier_logs", tmp_path)


def _ticket(description: str) -> SimpleNamespace:
    return SimpleNamespace(description=description)


CLASSIFICATION = SimpleNamespace(categorie="materiel", priorite="haute", confiance=0.9)


# --- Traces (OBS-1, OBS-4) ---------------------------------------------------
# Signature imposée par orchestrator.set_log_trace() (OBS-2) :
# (trace_id, ticket, classification, contexte, decision, latence_ms).


def test_trace_ecrite_puis_relue():
    log_trace(
        "t1", _ticket("mon écran est noir"), CLASSIFICATION, [],
        {"action": "resolution"}, 123.456,
    )
    traces = lire_dernieres_traces()

    assert len(traces) == 1
    assert traces[0]["trace_id"] == "t1"
    assert traces[0]["description"] == "mon écran est noir"
    assert traces[0]["categorie_classifiee"] == "materiel"
    assert traces[0]["decision"] == {"action": "resolution"}
    assert traces[0]["latence_ms"] == 123.5  # arrondi
    assert "horodatage" in traces[0]


def test_trace_avec_decision_pydantic_est_serialisee():
    """L'orchestrateur passe un vrai TicketDecision, pas un dict déjà aplati :
    model_dump() doit être appelé automatiquement."""
    from src.schemas import TicketDecision

    decision = TicketDecision(
        resume="r", categorie="materiel", priorite="basse", equipe="support_materiel",
        confiance=0.5, informations_manquantes=[], diagnostic="d", etapes_resolution=[],
        sources=[], outils_utilises=[], action="resolution", validation_humaine_requise=False,
    )
    log_trace("t1", _ticket("x"), None, [], decision, 1.0)
    assert lire_dernieres_traces()[0]["decision"]["categorie"] == "materiel"


def test_trace_sans_ticket_ni_classification():
    """Les garde-fous peuvent court-circuiter le pipeline avant que
    classification n'existe : ticket=None/classification=None ne doit pas
    planter le log."""
    log_trace("t1", None, None, None, {"action": "escalade"}, 1.0)
    trace = lire_dernieres_traces()[0]
    assert trace["description"] is None
    assert trace["categorie_classifiee"] is None
    assert trace["nb_documents_contexte"] == 0


def test_traces_les_plus_recentes_en_premier():
    log_trace("t1", _ticket("premier"), None, [], {}, 10)
    log_trace("t2", _ticket("second"), None, [], {}, 10)
    log_trace("t3", _ticket("troisieme"), None, [], {}, 10)

    traces = lire_dernieres_traces()
    assert [t["trace_id"] for t in traces] == ["t3", "t2", "t1"]


def test_limite_respectee():
    for i in range(5):
        log_trace(f"t{i}", _ticket("x"), None, [], {}, 1)
    assert len(lire_dernieres_traces(limite=2)) == 2


def test_aucun_fichier_ne_retourne_liste_vide():
    assert lire_dernieres_traces() == []


def test_trace_masque_les_donnees_sensibles():
    """SEC-5 : un mot de passe en clair dans la description ne doit jamais
    atterrir tel quel dans traces.jsonl."""
    log_trace("t1", _ticket("mon mot de passe est Ete2024!"), None, [], {}, 1)
    traces = lire_dernieres_traces()
    assert "Ete2024" not in traces[0]["description"]
    assert "***" in traces[0]["description"]


# --- Appels d'outils (OBS-1) -------------------------------------------------


def test_appel_outil_ecrit_puis_relu():
    log_tool_call(
        "t1", "rechercher_utilisateur", {"identifiant": "U-001"},
        {"statut": "trouve"}, "succes", 42.0,
    )
    appels = lire_derniers_appels_outils()

    assert len(appels) == 1
    assert appels[0]["outil"] == "rechercher_utilisateur"
    assert appels[0]["statut"] == "succes"
    assert appels[0]["trace_id"] == "t1"


def test_appel_outil_masque_les_parametres_sensibles():
    log_tool_call(
        "t1", "mettre_a_jour_ticket", {"champs": {"password": "secret123"}}, {}, "succes", 1,
    )
    appels = lire_derniers_appels_outils()
    assert "secret123" not in str(appels[0]["params"])


# --- Coût estimé (OBS-3) -----------------------------------------------------


def test_estimer_cout_calcul():
    cout = estimer_cout(1_000_000, 1_000_000)
    assert cout == pytest.approx(0.10 + 0.40)


def test_estimer_cout_sans_tokens_retourne_none():
    assert estimer_cout(None, None) is None
    assert estimer_cout(100, None) is None


# --- Appels LLM (OBS-6) ------------------------------------------------------


def test_appel_llm_ecrit_puis_relu():
    log_llm_call(
        prompt_systeme="Tu classifies des tickets.",
        contenu="Mon imprimante ne marche plus.",
        reponse_texte='{"categorie": "imprimantes"}',
        modele="gemini-3.5-flash-lite",
        latence_ms=250.0,
        tokens_entree=120,
        tokens_sortie=30,
        etape="classification",
        trace_id="t1",
    )
    appels = lire_derniers_appels_llm()

    assert len(appels) == 1
    assert appels[0]["etape"] == "classification"
    assert appels[0]["tokens_entree"] == 120
    assert appels[0]["cout_estime_usd"] == estimer_cout(120, 30)


def test_appel_llm_sans_tokens_cout_none():
    log_llm_call(
        prompt_systeme="s", contenu="u", reponse_texte="r",
        modele="m", latence_ms=1.0,
    )
    assert lire_derniers_appels_llm()[0]["cout_estime_usd"] is None


def test_appel_llm_masque_le_prompt_utilisateur():
    log_llm_call(
        prompt_systeme="s",
        contenu="mon mot de passe est Ete2024!",
        reponse_texte="r",
        modele="m",
        latence_ms=1.0,
    )
    assert "Ete2024" not in str(lire_derniers_appels_llm()[0]["contenu"])


# --- Chronomètre --------------------------------------------------------------


def test_chrono_latence_mesure_un_delai_positif():
    import time

    with ChronoLatence() as chrono:
        time.sleep(0.01)
    assert chrono.ms >= 10
