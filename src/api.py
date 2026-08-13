import uuid

from fastapi import FastAPI

from src.schemas import TicketDecision, TicketInput, TicketReponse

app = FastAPI(title="mAIntenance & Assistance")


@app.post("/tickets/traiter", response_model=TicketReponse)
async def traiter_ticket(ticket: TicketInput) -> TicketReponse:
    """Stub SETUP-5 : réponse factice codée en dur pour débloquer le frontend
    (FE-2) avant que le pipeline réel ne soit branché (voir ORCH-1)."""
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
    return TicketReponse(trace_id=trace_id, decision=decision)


@app.get("/health")
def health():
    return {"status": "ok"}
