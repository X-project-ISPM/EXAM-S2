from typing import Literal, get_args

from pydantic import BaseModel, Field, confloat

# --- Vocabulaires contrôlés -------------------------------------------------
# Définis une fois ici et réutilisés partout : le schéma de sortie structurée
# les impose au modèle côté serveur, ce qui rend impossible l'invention d'une
# catégorie ou d'un nom d'équipe, et rend l'évaluation reproductible.

Categorie = Literal[
    "comptes_authentification",
    "reseau",
    "materiel",
    "logiciels",
    "imprimantes",
    "droits_acces",
    "cybersecurite",
    "autre",
]

Priorite = Literal["basse", "moyenne", "haute", "critique"]

# À aligner sur la liste des services réellement fournie le jour du hackathon
# (§7 du sujet) ; seule la table EQUIPES_PAR_CATEGORIE dans classifier.py sera
# à ajuster.
Equipe = Literal[
    "support_niveau_1",
    "infrastructure_reseau",
    "support_materiel",
    "applications_metier",
    "gestion_identites",
    "securite_si",
]

Action = Literal["resolution", "demande_information", "escalade"]

CATEGORIES: tuple[str, ...] = get_args(Categorie)
PRIORITES: tuple[str, ...] = get_args(Priorite)
EQUIPES: tuple[str, ...] = get_args(Equipe)


# --- Entrée -----------------------------------------------------------------


class TicketInput(BaseModel):
    description: str
    utilisateur_id: str | None = None


# --- Étapes intermédiaires --------------------------------------------------


class AnalyseTicket(BaseModel):
    """Ce que le LLM produit à l'étape de classification.

    Volontairement sans `equipe` : le routage vers une équipe est une règle
    métier déterministe (table de correspondance), pas une tâche de
    compréhension du langage. Le sortir du périmètre du modèle rend le
    routage reproductible et auditable — et évite qu'il invente des noms
    d'équipes qui n'existent pas dans l'organisation.
    """

    categorie: Categorie
    priorite: Priorite
    confiance: confloat(ge=0, le=1) = Field(
        description="Certitude de la classification, 0 = incertain, 1 = certain"
    )
    incident_securite_avere: bool = Field(
        description=(
            "true uniquement si le ticket décrit un vrai risque ou incident de "
            "sécurité (phishing, poste compromis, intrusion). false pour une "
            "simple mention d'un outil de sécurité, par exemple une mise à jour "
            "d'antivirus qui ralentit le poste."
        )
    )
    justification: str = Field(description="Une phrase courte expliquant le choix")


class Classification(BaseModel):
    """Résultat complet de l'étape de classification (§3.1 du sujet)."""

    categorie: Categorie
    priorite: Priorite
    equipe: Equipe
    confiance: confloat(ge=0, le=1)
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


# --- Sortie -----------------------------------------------------------------


class TicketDecision(BaseModel):
    resume: str  # résumé du problème, exigé explicitement au §3.5 du sujet
    categorie: Categorie
    priorite: Priorite
    equipe: Equipe
    confiance: confloat(ge=0, le=1)
    informations_manquantes: list[str]
    diagnostic: str
    etapes_resolution: list[str]
    sources: list[str]
    outils_utilises: list[str]
    action: Action
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
