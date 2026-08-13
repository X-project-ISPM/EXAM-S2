"""API HTTP du projet (ORCH-1, ORCH-2, ORCH-4).

Le module reste volontairement mince : il traduit du HTTP vers le pipeline
(`src.orchestrator`) et retour. Toute la logique de traitement vit dans
l'orchestrateur, ce qui permet de la tester sans passer par le réseau.

Écart assumé avec le §2 de l'architecture : les endpoints sont déclarés `def`
et non `async def`. Le pipeline est entièrement synchrone et bloquant (appels
LLM, ChromaDB) ; en `async def` il figerait la boucle d'événements et
sérialiserait toutes les requêtes. En `def`, FastAPI l'exécute dans son
threadpool et l'API reste réactive — le `GET /health` répond même pendant le
traitement d'un ticket.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.agent import (
    charger_action_en_attente,
    executer_action_approuvee,
    rejeter_action_en_attente,
)
from src.config import config
from src.models import charger_toutes_les_donnees
from src.orchestrator import traiter_ticket
from src.schemas import TicketInput, TicketReponse, ValidationInput, ValidationReponse
from src.tools import initialiser_donnees


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Les outils lisent les données en mémoire (§1 de l'architecture) : sans ce
    # chargement au démarrage, tout appel d'outil échouerait en
    # « données non initialisées ». `charger_toutes_les_donnees()` tolère les
    # fichiers absents, l'API démarre donc même avec un `data/` incomplet.
    app.state.donnees = charger_toutes_les_donnees()
    initialiser_donnees(app.state.donnees)
    yield


app = FastAPI(title="mAIntenance & Assistance", lifespan=lifespan)


@app.post("/tickets/traiter", response_model=TicketReponse)
def traiter(ticket: TicketInput) -> TicketReponse:
    """Traite un ticket de bout en bout (ORCH-1).

    Retourne toujours 200 avec une décision valide : les échecs internes sont
    dégradés par l'orchestrateur (ORCH-3), jamais renvoyés en 500 nue.
    """
    return traiter_ticket(ticket)


@app.post("/tickets/valider", response_model=ValidationReponse)
def valider_action(validation: ValidationInput) -> ValidationReponse:
    """Confirme ou rejette une action sensible mise en attente par l'agent
    (ORCH-2, AGT-6).

    C'est le seul chemin par lequel une action sensible peut s'exécuter :
    `executer_action_approuvee()` est la seule fonction qui passe
    `approuve=True` à `executer_outil()`.

    Un `trace_id` sans action en attente n'est pas une erreur : un ticket peut
    exiger une validation humaine (escalade sécurité, confiance faible) sans
    qu'aucun outil n'ait été bloqué. On le dit explicitement plutôt que de
    renvoyer une 404 que le frontend afficherait comme une panne.
    """
    if charger_action_en_attente(validation.trace_id) is None:
        return ValidationReponse(
            statut="aucune_action_en_attente",
            message=(
                "Aucune action sensible n'était en attente pour cette trace : "
                "rien n'a été exécuté."
            ),
        )

    if not validation.approuve:
        rejeter_action_en_attente(validation.trace_id)
        return ValidationReponse(
            statut="rejete", message="Action rejetée par l'opérateur, rien n'a été exécuté."
        )

    resultat = executer_action_approuvee(validation.trace_id)
    if resultat.get("statut") != "succes":
        return ValidationReponse(
            statut="erreur",
            message=f"Action approuvée mais non exécutée : {resultat.get('message')}",
            resultat=resultat,
        )
    return ValidationReponse(
        statut="execute", message="Action approuvée et exécutée.", resultat=resultat
    )


@app.get("/observabilite/traces")
def observabilite_traces(limite: int = 50) -> list[dict]:
    """OBS-4 : les dernières traces, les plus récentes en premier — consommé
    par l'onglet Observabilité du frontend (FE-6)."""
    return lire_dernieres_traces(limite)


@app.get("/health")
def health():
    """État du service (ORCH-4).

    Volontairement sans appel LLM ni ouverture de l'index Chroma : un contrôle
    de santé doit répondre en quelques millisecondes et ne rien consommer du
    quota. Il expose ce qui explique le plus souvent une démo qui échoue — clé
    absente, données non chargées.
    """
    donnees = getattr(app.state, "donnees", None)
    return {
        "status": "ok",
        "modele": config.gemini_model,
        "cle_llm_configuree": bool(config.gemini_api_key),
        "donnees": {
            "utilisateurs": len(donnees.utilisateurs) if donnees else 0,
            "equipements": len(donnees.equipements) if donnees else 0,
            "services": len(donnees.services) if donnees else 0,
            "incidents_actifs": len(donnees.incidents_actifs) if donnees else 0,
            "articles_kb": len(donnees.kb) if donnees else 0,
        },
    }
