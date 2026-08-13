import json
from datetime import datetime

from pydantic import BaseModel

from src.config import config


class Utilisateur(BaseModel):
    id: str
    nom: str
    service: str
    equipements: list[str]  # ids des équipements associés


class Equipement(BaseModel):
    id: str
    type: str  # "poste", "imprimante", "serveur", ...
    utilisateur_id: str | None
    statut: str  # "actif", "en_panne", "maintenance"


class IncidentActif(BaseModel):
    id: str
    categorie: str
    service_affecte: str
    depuis: datetime
    tickets_lies: list[str]


class ArticleKB(BaseModel):
    id: str  # ex. "KB-NET-04"
    titre: str
    categorie: str
    contenu: str
    derniere_maj: datetime


class TicketHistorique(BaseModel):
    id: str
    description: str
    categorie: str
    priorite: str
    resolution: str | None
    duree_resolution_min: int | None


class Service(BaseModel):
    nom: str
    statut: str  # "operationnel", "degrade", "indisponible"


class BaseDeDonnees(BaseModel):
    """Toutes les ressources fournies, chargées en mémoire au démarrage de l'API."""

    utilisateurs: list[Utilisateur]
    equipements: list[Equipement]
    incidents_actifs: list[IncidentActif]
    kb: list[ArticleKB]
    tickets_historique: list[TicketHistorique]
    services: list[Service]


def _charger_json(nom_fichier: str) -> list[dict]:
    chemin = config.dossier_data / nom_fichier
    if not chemin.exists():
        # Les fichiers réels du hackathon ne sont pas encore déposés dans data/ ;
        # ne pas planter le démarrage de l'API pour autant.
        return []
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def charger_toutes_les_donnees(
    fichier_utilisateurs: str = "utilisateurs.json",
    fichier_equipements: str = "equipements.json",
    fichier_incidents: str = "incidents_actifs.json",
    fichier_kb: str = "kb.json",
    fichier_tickets: str = "tickets_historique.json",
    fichier_services: str = "services.json",
) -> BaseDeDonnees:
    """Point d'entrée unique appelé au démarrage de l'API (voir src/api.py).

    Noms de fichiers à ajuster pour correspondre exactement aux données
    fournies le jour du hackathon (§7 du sujet) si elles diffèrent."""
    return BaseDeDonnees(
        utilisateurs=[Utilisateur.model_validate(u) for u in _charger_json(fichier_utilisateurs)],
        equipements=[Equipement.model_validate(e) for e in _charger_json(fichier_equipements)],
        incidents_actifs=[
            IncidentActif.model_validate(i) for i in _charger_json(fichier_incidents)
        ],
        kb=[ArticleKB.model_validate(a) for a in _charger_json(fichier_kb)],
        tickets_historique=[
            TicketHistorique.model_validate(t) for t in _charger_json(fichier_tickets)
        ],
        services=[Service.model_validate(s) for s in _charger_json(fichier_services)],
    )
