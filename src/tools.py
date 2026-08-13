"""Spécification des 8 outils du §3.4 du sujet (AGT-1).

Une source de vérité unique, consommée par trois mécanismes :
- `declarer_outils()` : expose les outils au LLM (function calling natif Gemini) ;
- `valider_parametres()` / `executer_outil()` (AGT-4) : validation et exécution ;
- `est_sensible()` : règle de validation humaine, **déterministe côté code**.

Règle de conception (§9 de l'architecture) : la sensibilité d'un outil n'est
jamais laissée à l'appréciation du LLM. Même si un ticket manipulait le modèle
pour qu'il « décide » qu'une action n'est pas sensible, `est_sensible()` la
bloquerait de toute façon avant exécution.
"""

from typing import Any, Literal

from google.genai import types

from src.models import BaseDeDonnees

TypeOutil = Literal["consultation", "action"]


class OutilIndisponible(RuntimeError):
    """Les données (ou le registre de tickets) ne sont pas initialisés.

    L'API appelle `initialiser_donnees()` au démarrage ; dans les tests, la
    fixture la remplace par des données factices. Tant que ce n'est pas fait,
    aucun outil ne peut répondre — et `executer_outil()` (AGT-4) traduira
    cette erreur en statut exploitable par le LLM.
    """

# --- Spécification métier ----------------------------------------------------

OUTILS: list[dict] = [
    {
        "name": "rechercher_utilisateur",
        "type": "consultation",
        "sensible": False,
        "description": (
            "Recherche un utilisateur par nom, prénom ou identifiant, et retourne "
            "ses informations (service, équipements associés)."
        ),
        "parameters": {
            "identifiant": {
                "type": "STRING",
                "description": "Nom, prénom ou identifiant de l'utilisateur",
            }
        },
    },
    {
        "name": "consulter_equipement",
        "type": "consultation",
        "sensible": False,
        "description": (
            "Consulte l'état et les caractéristiques d'un équipement "
            "(poste, imprimante, serveur...)."
        ),
        "parameters": {
            "equipement_id": {
                "type": "STRING",
                "description": "Identifiant de l'équipement",
            }
        },
    },
    {
        "name": "verifier_etat_service",
        "type": "consultation",
        "sensible": False,
        "description": (
            "Vérifie si un service informatique est actuellement opérationnel, "
            "dégradé ou indisponible."
        ),
        "parameters": {
            "service": {
                "type": "STRING",
                "description": "Nom du service à vérifier",
            }
        },
    },
    {
        "name": "rechercher_incidents_actifs",
        "type": "consultation",
        "sensible": False,
        "description": (
            "Recherche les incidents actifs connus, éventuellement filtrés par "
            "catégorie ou service affecté. Permet de détecter un incident global "
            "plutôt qu'un cas isolé."
        ),
        "parameters": {
            "categorie": {
                "type": "STRING",
                "description": "Catégorie ou service pour filtrer (laisser vide pour tous)",
            }
        },
    },
    {
        "name": "creer_ticket",
        "type": "action",
        "sensible": False,
        "description": "Crée un nouveau ticket dans le système de gestion.",
        "parameters": {
            "description": {
                "type": "STRING",
                "description": "Description du problème",
            },
            "categorie": {
                "type": "STRING",
                "description": "Catégorie de l'incident",
            },
            "priorite": {
                "type": "STRING",
                "description": "Priorité : basse, moyenne, haute ou critique",
            },
        },
    },
    {
        "name": "mettre_a_jour_ticket",
        "type": "action",
        "sensible": True,
        "description": (
            "Met à jour le statut ou le contenu d'un ticket existant. "
            "Action sensible : une validation humaine est requise (§6 du sujet)."
        ),
        "parameters": {
            "ticket_id": {
                "type": "STRING",
                "description": "Identifiant du ticket à modifier",
            },
            "champs": {
                "type": "OBJECT",
                "description": "Champs à modifier (ex. statut, priorite, resolution)",
            },
        },
    },
    {
        "name": "affecter_ticket",
        "type": "action",
        "sensible": False,
        "description": "Affecte un ticket à une équipe de support.",
        "parameters": {
            "ticket_id": {
                "type": "STRING",
                "description": "Identifiant du ticket à affecter",
            },
            "equipe": {
                "type": "STRING",
                "description": "Nom de l'équipe destinataire",
            },
        },
    },
    {
        "name": "escalader_vers_technicien",
        "type": "action",
        "sensible": True,
        "description": (
            "Transmet le ticket à un technicien humain pour traitement manuel. "
            "Action sensible : une validation humaine est requise (§6 du sujet)."
        ),
        "parameters": {
            "ticket_id": {
                "type": "STRING",
                "description": "Identifiant du ticket à escalader",
            },
            "equipe": {
                "type": "STRING",
                "description": "Équipe du technicien destinataire",
            },
            "raison": {
                "type": "STRING",
                "description": "Motif de l'escalade",
            },
        },
    },
]

# --- Accès à la spécification ------------------------------------------------

_NOMS_OUTILS = {o["name"] for o in OUTILS}
_OUTILS_SENSIBLES = {o["name"] for o in OUTILS if o["sensible"]}


def spec_outil(nom: str) -> dict | None:
    """Retourne la spécification d'un outil, ou None s'il n'existe pas."""
    return next((o for o in OUTILS if o["name"] == nom), None)


def est_sensible(nom: str) -> bool:
    """Vrai si l'outil requiert une validation humaine avant exécution.

    Règle déterministe côté code : même un LLM manipulé ne peut pas la
    contourner (§9 de l'architecture, couche 3).
    """
    return nom in _OUTILS_SENSIBLES


# --- Déclaration pour le function calling Gemini -----------------------------


def declarer_outils() -> list[types.Tool]:
    """Convertit la spécification en déclarations exploitables par l'API Gemini.

    Tous les paramètres sont déclarés obligatoires (`required`) : le modèle ne
    peut pas omettre un champ, et `valider_parametres()` (AGT-4) s'appuie sur
    cette hypothèse pour ne vérifier que leur présence.
    """
    outils_declares = []
    for outil in OUTILS:
        proprietes = {
            nom: types.Schema(
                type=spec["type"],
                description=spec["description"],
            )
            for nom, spec in outil["parameters"].items()
        }
        outils_declares.append(
            types.FunctionDeclaration(
                name=outil["name"],
                description=outil["description"],
                parameters=types.Schema(
                    type="OBJECT",
                    properties=proprietes,
                    required=list(outil["parameters"]),
                ),
            )
        )
    return [types.Tool(function_declarations=outils_declares)]


# --- État en mémoire ---------------------------------------------------------
# Les données fournies sont chargées en mémoire au démarrage (SETUP-3) : les
# outils lisent ces structures, aucun SGBD n'est nécessaire (§1 de
# l'architecture). `_tickets_courants` est le registre des tickets "vivants"
# créés pendant la session (les tickets historiques, eux, sont en lecture
# seule).

_db: BaseDeDonnees | None = None
_tickets_courants: dict[str, dict[str, Any]] = {}
_compteur_tickets: int = 0


def initialiser_donnees(db: BaseDeDonnees) -> None:
    """Injection des données en mémoire. Appelée au démarrage de l'API."""
    global _db
    _db = db


def _base() -> BaseDeDonnees:
    if _db is None:
        raise OutilIndisponible(
            "Données non initialisées : initialiser_donnees() n'a pas été appelé."
        )
    return _db


# --- Outils de consultation (AGT-2) -----------------------------------------


def chercher_utilisateur(identifiant: str) -> dict:
    """Retourne les utilisateurs dont l'id ou le nom contient `identifiant`
    (insensible à la casse)."""
    texte = identifiant.strip().lower()
    utilisateurs = _base().utilisateurs
    trouves = [
        u for u in utilisateurs
        if texte in u.id.lower() or texte in u.nom.lower()
    ]
    if not trouves:
        return {"statut": "aucun_resultat", "message": f"Aucun utilisateur pour « {identifiant} »."}
    return {
        "statut": "trouve",
        "utilisateurs": [
            {"id": u.id, "nom": u.nom, "service": u.service, "equipements": u.equipements}
            for u in trouves
        ],
    }


def consulter_equipement(equipement_id: str) -> dict:
    """Retourne l'état et les caractéristiques d'un équipement, avec
    l'utilisateur auquel il est rattaché si c'est le cas."""
    texte = equipement_id.strip().lower()
    for equipement in _base().equipements:
        if texte in equipement.id.lower():
            utilisateur = None
            if equipement.utilisateur_id:
                for u in _base().utilisateurs:
                    if u.id == equipement.utilisateur_id:
                        utilisateur = {"id": u.id, "nom": u.nom, "service": u.service}
                        break
            return {
                "statut": "trouve",
                "equipement": {
                    "id": equipement.id,
                    "type": equipement.type,
                    "statut": equipement.statut,
                    "utilisateur": utilisateur,
                },
            }
    return {"statut": "aucun_resultat", "message": f"Équipement « {equipement_id} » introuvable."}


def verifier_etat_service(service: str) -> dict:
    """Retourne l'état opérationnel d'un service (insensible à la casse)."""
    texte = service.strip().lower()
    for s in _base().services:
        if texte in s.nom.lower():
            return {"statut": "trouve", "service": s.nom, "etat": s.statut}
    return {"statut": "aucun_resultat", "message": f"Service « {service} » inconnu."}


def rechercher_incidents_actifs(categorie: str = "") -> dict:
    """Recherche les incidents actifs, filtrés par catégorie ou service
    affecté. Permet de distinguer un incident global d'un cas isolé
    (scénario 2 du sujet)."""
    filtre = categorie.strip().lower()
    incidents = _base().incidents_actifs
    trouves = [
        i for i in incidents
        if not filtre
        or filtre in i.categorie.lower()
        or filtre in i.service_affecte.lower()
    ]
    if not trouves:
        return {"statut": "aucun_resultat", "message": "Aucun incident actif."}
    return {
        "statut": "trouve",
        "incidents": [
            {
                "id": i.id,
                "categorie": i.categorie,
                "service_affecte": i.service_affecte,
                "depuis": i.depuis.isoformat(),
                "tickets_lies": i.tickets_lies,
            }
            for i in trouves
        ],
    }


# --- Outils d'action (AGT-3) -------------------------------------------------
# Ces outils écrivent dans le registre `_tickets_courants` (état de session) :
# la base de données fournie reste en lecture seule, c'est un système simulé.
# `mettre_a_jour_ticket` et `escalader_vers_technicien` sont sensibles : leur
# exécution réelle est précédée d'une validation humaine (AGT-6).


def _prochain_id_ticket() -> str:
    global _compteur_tickets
    _compteur_tickets += 1
    return f"TK-{_compteur_tickets:04d}"


def creer_ticket(description: str, categorie: str, priorite: str) -> dict:
    """Crée un ticket dans le registre de session et retourne son id."""
    identifiant = _prochain_id_ticket()
    _tickets_courants[identifiant] = {
        "id": identifiant,
        "description": description,
        "categorie": categorie,
        "priorite": priorite,
        "statut": "ouvert",
    }
    return {
        "statut": "succes",
        "ticket": _tickets_courants[identifiant],
    }


def _ticket_existant(ticket_id: str) -> dict:
    ticket = _tickets_courants.get(ticket_id.strip())
    if ticket is None:
        raise ValueError(
            f"Ticket « {ticket_id} » introuvable dans le registre de session. "
            "Utiliser d'abord creer_ticket pour l'ajouter."
        )
    return ticket


def mettre_a_jour_ticket(ticket_id: str, champs: dict) -> dict:
    """Modifie les champs fournis (statut, priorite, resolution...) d'un
    ticket de session. Action sensible : validation humaine requise."""
    ticket = _ticket_existant(ticket_id)
    champs_connus = {
        k: v
        for k, v in champs.items()
        if k in ticket or k in ("statut", "resolution", "equipe")
    }
    ticket.update(champs_connus)
    return {"statut": "succes", "ticket": ticket}


def affecter_ticket(ticket_id: str, equipe: str) -> dict:
    """Affecte un ticket de session à une équipe de support."""
    ticket = _ticket_existant(ticket_id)
    ticket["equipe"] = equipe
    return {"statut": "succes", "ticket": ticket}


def escalader_vers_technicien(ticket_id: str, equipe: str, raison: str) -> dict:
    """Transmet le ticket à un technicien humain. Action sensible : validation
    humaine requise."""
    ticket = _ticket_existant(ticket_id)
    ticket["statut"] = "escalade"
    ticket["equipe"] = equipe
    ticket["raison_escalade"] = raison
    return {"statut": "succes", "ticket": ticket}


# --- Registre des exécutions (AGT-4) -----------------------------------------
# La sensibilité n'est pas évaluée ici : `est_sensible()` est décidée côté
# code (voir plus haut) et `executer_outil()` (AGT-4) s'en sert avant tout
# appel réel.

TOOL_REGISTRY: dict[str, Any] = {
    "rechercher_utilisateur": chercher_utilisateur,
    "consulter_equipement": consulter_equipement,
    "verifier_etat_service": verifier_etat_service,
    "rechercher_incidents_actifs": rechercher_incidents_actifs,
    "creer_ticket": creer_ticket,
    "mettre_a_jour_ticket": mettre_a_jour_ticket,
    "affecter_ticket": affecter_ticket,
    "escalader_vers_technicien": escalader_vers_technicien,
}


# --- Validation et exécution (AGT-4) -----------------------------------------
# Point de passage unique de tous les appels d'outils : c'est ici que
# s'appliquent, dans l'ordre, la validation des paramètres, la règle de
# sensibilité côté code, puis l'exécution avec capture d'erreur — et c'est ici
# que chaque appel est enregistré (observabilité, §5.4 du sujet).


def valider_parametres(nom: str, params: dict) -> bool:
    """Vrai si `params` contient tous les paramètres requis par la spéc.

    Tous les paramètres sont déclarés obligatoires dans `declarer_outils()` :
    un appel incomplet est un appel invalide, refusé avant exécution."""
    specification = spec_outil(nom)
    if specification is None:
        return False
    return all(cle in params for cle in specification["parameters"])


# Hook d'observabilité : `log_tool_call` de src/observability sera branché ici
# par OBS-1. Tant que le module n'existe pas, on reste silencieux plutôt que de
# créer une dépendance circulaire.
_log_appel: Any = None


def set_log_appel(fonction) -> None:
    """Branche le logger d'appels d'outils (OBS-1). Signature attendue :
    `fonction(trace_id, nom, params, resultat, statut, latence_ms)`."""
    global _log_appel
    _log_appel = fonction


def executer_outil(nom: str, params: dict, trace_id: str, approuve: bool = False) -> dict:
    """Valide puis exécute un outil, en retournant un statut exploitable par
    l'agent (jamais d'exception qui remonte jusqu'à l'utilisateur) :
    - `erreur` : outil inconnu, paramètres manquants, ou exception levée ;
    - `attente_validation_humaine` : outil sensible, bloqué avant exécution ;
    - `succes` : résultat de l'outil.

    `approuve=True` n'est utilisable que depuis `executer_action_approuvee`
    (AGT-6 / ORCH-2), après qu'un humain a validé l'action en attente : c'est
    le seul chemin qui lève le blocage de sensibilité.
    """
    import time

    t0 = time.time()

    if spec_outil(nom) is None:
        return {"statut": "erreur", "message": f"Outil inconnu : {nom}"}

    if not valider_parametres(nom, params):
        manquants = [
            cle for cle in spec_outil(nom)["parameters"] if cle not in params
        ]
        return {
            "statut": "erreur",
            "message": f"Paramètres manquants ou invalides pour {nom} : {manquants}",
        }

    if est_sensible(nom) and not approuve:
        return {"statut": "attente_validation_humaine", "outil": nom, "params": params}

    try:
        resultat = TOOL_REGISTRY[nom](**params)
        statut, contenu = "succes", resultat
    except Exception as e:
        statut, contenu = "erreur", str(e)

    if _log_appel is not None:
        _log_appel(trace_id, nom, params, contenu, statut, round((time.time() - t0) * 1000))

    return {"statut": statut, "resultat" if statut == "succes" else "message": contenu}
