"""Tests de l'API HTTP (ORCH-1, ORCH-2, ORCH-4), sans réseau ni clé LLM.

Le pipeline (classification, diagnostic, RAG, agent) est remplacé par des
doubles au niveau de `src.orchestrator`, avec le même principe que
`test_orchestrator.py` : ces tests vérifient le contrat HTTP exposé au
frontend (enveloppe, schéma, `/tickets/valider`, `/health`), pas la qualité
des réponses du modèle. Sans ce court-circuit, chaque test déclencherait un
appel réel à Gemini via l'orchestrateur — exactement ce que le marqueur
`reseau` est censé éviter par défaut (`pyproject.toml`).
"""

import pytest
from fastapi.testclient import TestClient
from src.api import app
from src.config import config
from src.models import BaseDeDonnees
from src.schemas import Classification, DiagnosticInfo, TicketDecision
from src.tools import creer_ticket, initialiser_donnees

from src import agent, orchestrator

SAIN = {"danger": False, "raison": None, "couche": None, "verification_llm": "ok"}

CLASSIFICATION = Classification(
    categorie="materiel",
    priorite="basse",
    equipe="support_materiel",
    confiance=0.8,
    justification="test",
)


def _decision(**champs) -> TicketDecision:
    base = dict(
        resume="Ticket reçu",
        categorie="materiel",
        priorite="basse",
        equipe="support_materiel",
        confiance=0.8,
        informations_manquantes=[],
        diagnostic="ok",
        etapes_resolution=[],
        sources=[],
        outils_utilises=[],
        action="resolution",
        validation_humaine_requise=False,
    )
    base.update(champs)
    return TicketDecision(**base)


@pytest.fixture(autouse=True)
def pipeline(monkeypatch):
    """Court-circuite les cinq étapes du pipeline pour tous les tests de ce
    fichier — aucun n'a besoin du vrai LLM pour vérifier un contrat HTTP."""
    monkeypatch.setattr(orchestrator, "check_injection", lambda texte, avec_llm=True: dict(SAIN))
    monkeypatch.setattr(orchestrator, "classify_ticket", lambda description: CLASSIFICATION)
    monkeypatch.setattr(
        orchestrator,
        "extraire_diagnostic",
        lambda description, categorie=None: DiagnosticInfo(informations_manquantes=[]),
    )
    monkeypatch.setattr(
        orchestrator,
        "retrieve_context",
        lambda description, categorie=None, k=None, seuil=None: [],
    )
    # `resume` reprend la description reçue par l'agent : permet de vérifier
    # qu'une chaîne UTF-8 traverse tout le pipeline sans être altérée, sans
    # pour autant tester le contenu réel produit par le LLM.
    monkeypatch.setattr(
        orchestrator,
        "run_agent",
        lambda description, *args, **kwargs: _decision(resume=f"Ticket reçu : {description}"),
    )


@pytest.fixture(autouse=True)
def _logs_isoles(tmp_path, monkeypatch):
    """Le `lifespan` branche pour de vrai les hooks OBS-1/2/6 (`set_log_appel`,
    `set_log_llm_call`, `orchestrator.set_log_trace`) : sans cette isolation,
    chaque test ici écrirait dans le vrai `logs/` du dépôt."""
    monkeypatch.setattr(config, "dossier_logs", tmp_path)


@pytest.fixture
def client():
    # Contexte requis pour déclencher le `lifespan` (chargement des données,
    # `initialiser_donnees`, branchement des hooks d'observabilité) : sans
    # lui, `app.state.donnees` n'existe jamais et rien n'est loggé.
    with TestClient(app) as c:
        yield c


def test_health(client):
    reponse = client.get("/health")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["status"] == "ok"
    assert "donnees" in corps
    assert "cle_llm_configuree" in corps


def test_traiter_retourne_enveloppe_avec_trace_id(client):
    reponse = client.post("/tickets/traiter", json={"description": "Mon écran ne s'allume plus"})
    assert reponse.status_code == 200

    corps = reponse.json()
    assert "trace_id" in corps
    assert "decision" in corps
    # Le frontend lit reponse["trace_id"], jamais decision["trace_id"].
    assert "trace_id" not in corps["decision"]


def test_traiter_respecte_le_schema_du_sujet(client):
    corps = client.post("/tickets/traiter", json={"description": "Test"}).json()
    attendus = {
        "resume", "categorie", "priorite", "equipe", "confiance",
        "informations_manquantes", "diagnostic", "etapes_resolution",
        "sources", "outils_utilises", "action", "validation_humaine_requise",
    }
    assert attendus <= set(corps["decision"])


def test_trace_id_unique_par_ticket(client):
    premier = client.post("/tickets/traiter", json={"description": "A"}).json()["trace_id"]
    second = client.post("/tickets/traiter", json={"description": "B"}).json()["trace_id"]
    assert premier != second


def test_description_manquante_est_rejetee(client):
    assert client.post("/tickets/traiter", json={}).status_code == 422


def test_accents_preserves(client):
    """Les tickets sont en français : vérifie qu'aucune étape ne casse l'UTF-8."""
    corps = client.post(
        "/tickets/traiter", json={"description": "Problème d'accès à l'imprimante"}
    ).json()
    assert "Problème d'accès" in corps["decision"]["resume"]


def test_confiance_de_la_classification_traverse_lapi(client):
    """Un contrôle bout-en-bout qu'une valeur produite par le pipeline (et pas
    juste le squelette de l'enveloppe) atteint bien la réponse HTTP."""
    corps = client.post("/tickets/traiter", json={"description": "Poste en panne"}).json()
    assert corps["decision"]["categorie"] == "materiel"
    assert corps["decision"]["equipe"] == "support_materiel"


# --- GET /observabilite/traces (OBS-2, OBS-4) --------------------------------


def test_observabilite_traces_vide_sans_ticket_traite(client):
    assert client.get("/observabilite/traces").json() == []


def test_traiter_ecrit_une_trace_lisible_par_observabilite(client):
    """OBS-2 : le hook `orchestrator.set_log_trace()` est bien branché par le
    `lifespan` — même le pipeline réel (pas juste le stub d'avant ORCH-1) doit
    produire une trace exploitable pour l'onglet Observabilité (FE-6)."""
    trace_id = client.post("/tickets/traiter", json={"description": "Test OBS"}).json()["trace_id"]

    traces = client.get("/observabilite/traces").json()
    trace = next(t for t in traces if t["trace_id"] == trace_id)
    assert trace["categorie_classifiee"] == "materiel"
    assert trace["decision"]["categorie"] == "materiel"
    assert trace["latence_ms"] >= 0


def test_observabilite_traces_respecte_la_limite(client):
    for i in range(3):
        client.post("/tickets/traiter", json={"description": f"ticket {i}"})
    assert len(client.get("/observabilite/traces", params={"limite": 2}).json()) == 2


# --- POST /tickets/valider (ORCH-2) ------------------------------------------


@pytest.fixture(autouse=True)
def _donnees_outils():
    """Registre en mémoire nécessaire à `creer_ticket` / `mettre_a_jour_ticket`
    (AGT-2/3), utilisés par les tests de validation ci-dessous."""
    initialiser_donnees(
        BaseDeDonnees(
            utilisateurs=[], equipements=[], incidents_actifs=[], kb=[],
            tickets_historique=[], services=[],
        )
    )


def test_validation_approuvee_execute_laction_en_attente(client):
    ticket_id = creer_ticket("pb", "materiel", "basse")["ticket"]["id"]
    trace_id = client.post("/tickets/traiter", json={"description": "Poste en panne"}).json()[
        "trace_id"
    ]
    agent.sauvegarder_action_en_attente(
        trace_id,
        {
            "outil": "mettre_a_jour_ticket",
            "params": {"ticket_id": ticket_id, "champs": {"statut": "ferme"}},
        },
    )

    reponse = client.post("/tickets/valider", json={"trace_id": trace_id, "approuve": True})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["statut"] == "execute"
    assert corps["resultat"]["resultat"]["ticket"]["statut"] == "ferme"
    assert agent.charger_action_en_attente(trace_id) is None


def test_validation_rejetee_nexecute_rien(client):
    agent.sauvegarder_action_en_attente("trace-rejet", {"outil": "x", "params": {}})

    reponse = client.post("/tickets/valider", json={"trace_id": "trace-rejet", "approuve": False})
    assert reponse.status_code == 200
    assert reponse.json()["statut"] == "rejete"
    assert agent.charger_action_en_attente("trace-rejet") is None


def test_validation_sans_action_en_attente_nest_pas_une_erreur(client):
    """Un ticket peut exiger une validation humaine sans qu'aucun outil
    sensible n'ait été bloqué (ex. escalade sécurité) : ce n'est pas un 404."""
    reponse = client.post(
        "/tickets/valider", json={"trace_id": "trace-inconnue", "approuve": True}
    )
    assert reponse.status_code == 200
    assert reponse.json()["statut"] == "aucune_action_en_attente"
