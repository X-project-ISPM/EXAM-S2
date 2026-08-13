from typing import Literal

from pydantic import BaseModel, confloat


class TicketInput(BaseModel):
    description: str
    utilisateur_id: str | None = None


class Classification(BaseModel):
    categorie: Literal[
        "comptes_authentification", "reseau", "materiel",
        "logiciels", "imprimantes", "droits_acces",
        "cybersecurite", "autre",
    ]
    priorite: Literal["basse", "moyenne", "haute", "critique"]
    equipe: str
    justification: str


class DiagnosticInfo(BaseModel):
    utilisateur: str | None = None
    equipement: str | None = None
    application: str | None = None
    symptomes: str | None = None
    moment_apparition: str | None = None
    impact: str | None = None
    manipulations_effectuees: str | None = None
    informations_manquantes: list[str]


class TicketDecision(BaseModel):
    resume: str  # résumé du problème, exigé explicitement au §3.5 du sujet
    categorie: str
    priorite: Literal["basse", "moyenne", "haute", "critique"]
    equipe: str
    confiance: confloat(ge=0, le=1)
    informations_manquantes: list[str]
    diagnostic: str
    etapes_resolution: list[str]
    sources: list[str]
    outils_utilises: list[str]
    action: Literal["resolution", "demande_information", "escalade"]
    validation_humaine_requise: bool


class TicketReponse(BaseModel):
    """Enveloppe retournée par POST /tickets/traiter.

    `trace_id` est une métadonnée de routage (nécessaire pour POST
    /tickets/valider et pour relier la décision affichée à sa trace
    d'observabilité) : elle n'apparaît pas dans l'exemple JSON du §5.3 du
    sujet et ne doit donc pas polluer TicketDecision, qui reste exactement
    la "décision exploitable, justifiée et contrôlable" attendue."""

    trace_id: str
    decision: TicketDecision
