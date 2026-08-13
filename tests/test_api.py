"""Tests de l'API HTTP, sans réseau ni clé LLM.

Ils garantissent que le contrat exposé au frontend reste stable pendant que
l'orchestrateur réel (ORCH-1) remplace progressivement le stub.
"""

import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.config import config

client = TestClient(app)


@pytest.fixture(autouse=True)
def _logs_isoles(tmp_path, monkeypatch):
    """Les traces écrites par le stub (OBS-1) ne doivent pas polluer logs/
    ni fuiter d'un test à l'autre."""
    monkeypatch.setattr(config, "dossier_logs", tmp_path)


def test_health():
    reponse = client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json() == {"status": "ok"}


def test_traiter_retourne_enveloppe_avec_trace_id():
    reponse = client.post("/tickets/traiter", json={"description": "Mon écran ne s'allume plus"})
    assert reponse.status_code == 200

    corps = reponse.json()
    assert "trace_id" in corps
    assert "decision" in corps
    # Le frontend lit reponse["trace_id"], jamais decision["trace_id"].
    assert "trace_id" not in corps["decision"]


def test_traiter_respecte_le_schema_du_sujet():
    corps = client.post("/tickets/traiter", json={"description": "Test"}).json()
    attendus = {
        "resume", "categorie", "priorite", "equipe", "confiance",
        "informations_manquantes", "diagnostic", "etapes_resolution",
        "sources", "outils_utilises", "action", "validation_humaine_requise",
    }
    assert attendus <= set(corps["decision"])


def test_trace_id_unique_par_ticket():
    premier = client.post("/tickets/traiter", json={"description": "A"}).json()["trace_id"]
    second = client.post("/tickets/traiter", json={"description": "B"}).json()["trace_id"]
    assert premier != second


def test_description_manquante_est_rejetee():
    assert client.post("/tickets/traiter", json={}).status_code == 422


def test_accents_preserves():
    """Les tickets sont en français : vérifie qu'aucune étape ne casse l'UTF-8."""
    corps = client.post(
        "/tickets/traiter", json={"description": "Problème d'accès à l'imprimante"}
    ).json()
    assert "Problème d'accès" in corps["decision"]["resume"]


def test_traiter_ecrit_une_trace_lisible_par_observabilite():
    """OBS-1/OBS-4 : même le stub doit produire une trace exploitable, pour
    que l'onglet Observabilité du frontend (FE-6) ait des données avant ORCH-1."""
    trace_id = client.post("/tickets/traiter", json={"description": "Test OBS"}).json()["trace_id"]

    traces = client.get("/observabilite/traces").json()
    assert any(t["trace_id"] == trace_id for t in traces)


def test_observabilite_traces_vide_sans_ticket_traite():
    assert client.get("/observabilite/traces").json() == []


def test_observabilite_traces_respecte_la_limite():
    for i in range(3):
        client.post("/tickets/traiter", json={"description": f"ticket {i}"})
    assert len(client.get("/observabilite/traces", params={"limite": 2}).json()) == 2
