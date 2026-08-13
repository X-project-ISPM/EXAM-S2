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
from src.llm_client import set_log_llm_call
from src.models import charger_toutes_les_donnees
from src.observability import (
    lire_dernieres_traces,
    log_llm_call,
    log_tool_call,
    log_trace,
)
from src.orchestrator import set_log_trace, traiter_ticket
from src.schemas import TicketInput, TicketReponse, ValidationInput, ValidationReponse
from src.tools import initialiser_donnees, set_log_appel


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Les outils lisent les données en mémoire (§1 de l'architecture) : sans ce
    # chargement au démarrage, tout appel d'outil échouerait en
    # « données non initialisées ». `charger_toutes_les_donnees()` tolère les
    # fichiers absents, l'API démarre donc même avec un `data/` incomplet.
    app.state.donnees = charger_toutes_les_donnees()
    initialiser_donnees(app.state.donnees)
    # OBS-1/OBS-2/OBS-6 : brancher les trois loggers une fois au démarrage.
    # Hooks plutôt qu'imports directs dans tools.py/llm_client.py/
    # orchestrator.py — observability.py importe guardrails.py, qui importe
    # déjà llm_client.py (cycle si l'import était direct).
    set_log_appel(log_tool_call)
    set_log_llm_call(log_llm_call)
    set_log_trace(log_trace)

    # Ingestion automatique du corpus RAG s'il est vide au démarrage
    import logging
    logger = logging.getLogger("src.api")
    try:
        from src.rag import ingerer, nombre_de_fragments
        if nombre_de_fragments() == 0 and app.state.donnees.kb:
            logger.info("ChromaDB est vide, ingestion automatique de la KB...")
            ingerer(app.state.donnees.kb, reinitialiser=True)
            logger.info(f"Ingestion réussie : {nombre_de_fragments()} fragments indexés.")
    except Exception as e:
        logger.exception("Échec de l'ingestion automatique de la KB au démarrage")

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


@app.get("/health/diagnostic")
def health_diagnostic(test: str | None = None):
    """Effectue des tests diagnostics ciblés (Gemini, ChromaDB, Données) (ORCH-4).

    Permet au frontend d'identifier précisément quel composant échoue ou crash
    (notamment le crash OOM de ChromaDB/SentenceTransformers sur Render).
    """
    if test == "gemini":
        try:
            from src.llm_client import llm_call
            reponse = llm_call(
                prompt_systeme="Tu es un système de diagnostic. Réponds uniquement par 'OK'.",
                prompt_utilisateur="test",
                etape="diagnostic",
            )
            valide = "ok" in str(reponse).lower()
            return {"status": "ok" if valide else "error", "details": str(reponse)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif test == "chromadb":
        try:
            from src.rag import nombre_de_fragments
            nb = nombre_de_fragments()
            return {"status": "ok", "fragments": nb}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif test == "data":
        dossier = config.dossier_data
        resultats = {}
        fichiers = [
            "utilisateurs.json",
            "equipements.json",
            "incidents_actifs.json",
            "kb.json",
            "tickets_historique.json",
            "services.json",
        ]
        for fichier in fichiers:
            chemin = dossier / fichier
            resultats[fichier] = {
                "existe": chemin.exists(),
                "taille_bytes": chemin.stat().st_size if chemin.exists() else 0,
            }
        return {"status": "ok", "fichiers": resultats}

    else:
        return {
            "status": "ok",
            "message": "Spécifiez ?test=gemini, ?test=chromadb ou ?test=data pour lancer un test.",
        }

