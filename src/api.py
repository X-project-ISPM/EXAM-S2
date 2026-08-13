import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.llm_client import set_log_llm_call
from src.observability import lire_dernieres_traces, log_llm_call, log_tool_call, log_trace
from src.schemas import TicketDecision, TicketInput, TicketReponse
from src.tools import set_log_appel


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # OBS-1/OBS-6 : brancher les loggers d'observabilité une fois au démarrage
    # plutôt qu'à chaque requête. Hooks plutôt qu'imports directs dans
    # tools.py/llm_client.py — voir le commentaire sur set_log_llm_call pour
    # la raison (cycle d'imports via guardrails.py).
    set_log_appel(log_tool_call)
    set_log_llm_call(log_llm_call)
    yield


app = FastAPI(title="mAIntenance & Assistance", lifespan=_lifespan)


@app.post("/tickets/traiter", response_model=TicketReponse)
async def traiter_ticket(ticket: TicketInput) -> TicketReponse:
    """Stub SETUP-5 : réponse factice codée en dur pour débloquer le frontend
    (FE-2) avant que le pipeline réel ne soit branché (voir ORCH-1).

    Journalise quand même une trace (OBS-1) : l'onglet Observabilité du
    frontend (FE-6) et GET /observabilite/traces (OBS-4) ont ainsi de vraies
    données à afficher dès maintenant, sans attendre ORCH-1.
    """
    debut = time.perf_counter()
    trace_id = str(uuid.uuid4())
    decision = TicketDecision(
        resume=f"Ticket reçu : {ticket.description[:120]}",
        categorie="autre",
        priorite="basse",
        equipe="support_niveau_1",
        confiance=0.0,
        informations_manquantes=[],
        diagnostic="Stub SETUP-5 — pipeline réel non encore branché (voir ORCH-1).",
        etapes_resolution=[],
        sources=[],
        outils_utilises=[],
        action="demande_information",
        validation_humaine_requise=False,
    )
    latence_ms = (time.perf_counter() - debut) * 1000
    log_trace(trace_id, ticket.description, decision.model_dump(), latence_ms)
    return TicketReponse(trace_id=trace_id, decision=decision)


@app.get("/observabilite/traces")
def observabilite_traces(limite: int = 50) -> list[dict]:
    """OBS-4 : les dernières traces, les plus récentes en premier — consommé
    par l'onglet Observabilité du frontend (FE-6)."""
    return lire_dernieres_traces(limite)


@app.get("/health")
def health():
    return {"status": "ok"}
