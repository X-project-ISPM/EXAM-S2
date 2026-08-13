"""Tests de la spécification des outils (AGT-1).

La spécification est un contrat : elle doit rester stable et cohérente, car
`declarer_outils()` l'expose au LLM, `valider_parametres()` (AGT-4) la
consomme, et `est_sensible()` décide de la validation humaine.
"""

from datetime import datetime

import pytest

from src.models import (
    ArticleKB,
    BaseDeDonnees,
    Equipement,
    IncidentActif,
    Service,
    TicketHistorique,
    Utilisateur,
)
from src.tools import (
    OUTILS,
    TOOL_REGISTRY,
    _tickets_courants,
    affecter_ticket,
    chercher_utilisateur,
    consulter_equipement,
    creer_ticket,
    declarer_outils,
    escalader_vers_technicien,
    est_sensible,
    executer_outil,
    initialiser_donnees,
    mettre_a_jour_ticket,
    rechercher_incidents_actifs,
    set_log_appel,
    spec_outil,
    valider_parametres,
    verifier_etat_service,
)


@pytest.fixture
def base_factice():
    """Base de données en mémoire, calquée sur la structure fournie (§7)."""
    return BaseDeDonnees(
        utilisateurs=[
            Utilisateur(
                id="U-001",
                nom="Rakoto Hery",
                service="comptabilite",
                equipements=["PC-001"],
            ),
            Utilisateur(id="U-002", nom="Rabe Lala", service="rh", equipements=[]),
        ],
        equipements=[
            Equipement(id="PC-001", type="poste", utilisateur_id="U-001", statut="en_panne"),
            Equipement(id="IMP-001", type="imprimante", utilisateur_id=None, statut="actif"),
        ],
        incidents_actifs=[
            IncidentActif(
                id="INC-01",
                categorie="reseau",
                service_affecte="tous",
                depuis=datetime(2026, 8, 13, 9, 0),
                tickets_lies=["H-42"],
            )
        ],
        kb=[
            ArticleKB(
                id="KB-NET-04",
                titre="Coupure réseau",
                categorie="reseau",
                contenu="...",
                derniere_maj=datetime(2026, 8, 1),
            )
        ],
        tickets_historique=[
            TicketHistorique(
                id="H-42",
                description="impossible de joindre le serveur",
                categorie="reseau",
                priorite="haute",
                resolution=None,
                duree_resolution_min=None,
            )
        ],
        services=[
            Service(nom="reseau", statut="degrade"),
            Service(nom="messagerie", statut="operationnel"),
        ],
    )


@pytest.fixture
def outils_initialises(base_factice):
    initialiser_donnees(base_factice)
    return base_factice


# --- Spécification (AGT-1) --------------------------------------------------


def test_exactement_8_outils():
    assert len(OUTILS) == 8


def test_noms_identiques_a_ceux_du_sujet():
    """§3.4 du sujet : les 8 noms exacts, sans renommage."""
    attendus = {
        "rechercher_utilisateur",
        "consulter_equipement",
        "verifier_etat_service",
        "rechercher_incidents_actifs",
        "creer_ticket",
        "mettre_a_jour_ticket",
        "affecter_ticket",
        "escalader_vers_technicien",
    }
    assert {o["name"] for o in OUTILS} == attendus


def test_noms_uniques():
    assert len({o["name"] for o in OUTILS}) == len(OUTILS)


def test_4_consultations_et_4_actions():
    par_type = {o["type"] for o in OUTILS}
    assert par_type == {"consultation", "action"}
    assert sum(o["type"] == "consultation" for o in OUTILS) == 4
    assert sum(o["type"] == "action" for o in OUTILS) == 4


def test_seuls_les_2_outils_d_action_sensibles_le_sont():
    """§6 du sujet : modification de ticket et escalade sont sensibles ;
    une consultation ou une création de ticket ne le sont pas."""
    sensibles = {o["name"] for o in OUTILS if o["sensible"]}
    assert sensibles == {"mettre_a_jour_ticket", "escalader_vers_technicien"}


def test_chaque_outil_a_des_parameters_non_vides():
    for outil in OUTILS:
        assert outil["parameters"], outil["name"]


def test_est_sensible_coherent_avec_la_spec():
    for outil in OUTILS:
        assert est_sensible(outil["name"]) == outil["sensible"]


def test_est_sensible_retourne_faux_pour_une_spec_inconnue():
    assert not est_sensible("outil_qui_nexiste_pas")


def test_spec_outil_inconnu_retourne_none():
    assert spec_outil("nimporte_quoi") is None


def test_declaration_gemini_complete():
    tools = declarer_outils()
    assert len(tools) == 1
    declares = {d.name for d in tools[0].function_declarations}
    assert declares == {o["name"] for o in OUTILS}


def test_declaration_gemini_marque_tous_les_parametres_obligatoires():
    """La validation de paramètres (AGT-4) s'appuie sur le fait que rien n'est
    optionnel : vérifier que la déclaration le reflète bien."""
    for outil in OUTILS:
        declaration = next(
            d
            for d in declarer_outils()[0].function_declarations
            if d.name == outil["name"]
        )
        assert set(declaration.parameters.required) == set(outil["parameters"])

# --- Outils de consultation (AGT-2) -----------------------------------------


def test_chercher_utilisateur_par_id(outils_initialises):
    resultat = chercher_utilisateur("U-001")
    assert resultat["statut"] == "trouve"
    assert resultat["utilisateurs"][0]["nom"] == "Rakoto Hery"
    assert resultat["utilisateurs"][0]["equipements"] == ["PC-001"]


def test_chercher_utilisateur_insensible_a_la_casse_et_au_nom(outils_initialises):
    resultat = chercher_utilisateur("rakoto")
    assert resultat["statut"] == "trouve"
    assert resultat["utilisateurs"][0]["id"] == "U-001"


def test_chercher_utilisateur_inconnu(outils_initialises):
    resultat = chercher_utilisateur("personne")
    assert resultat["statut"] == "aucun_resultat"


def test_consulter_equipement(outils_initialises):
    resultat = consulter_equipement("PC-001")
    assert resultat["statut"] == "trouve"
    assert resultat["equipement"]["type"] == "poste"
    assert resultat["equipement"]["statut"] == "en_panne"
    assert resultat["equipement"]["utilisateur"]["nom"] == "Rakoto Hery"


def test_consulter_equipement_inconnu(outils_initialises):
    resultat = consulter_equipement("SERVEUR-X")
    assert resultat["statut"] == "aucun_resultat"


def test_verifier_etat_service(outils_initialises):
    resultat = verifier_etat_service("reseau")
    assert resultat["statut"] == "trouve"
    assert resultat["etat"] == "degrade"


def test_verifier_etat_service_insensible_a_la_casse(outils_initialises):
    assert verifier_etat_service("MESSAGERIE")["etat"] == "operationnel"


def test_verifier_etat_service_inconnu(outils_initialises):
    assert verifier_etat_service("téléphonie")["statut"] == "aucun_resultat"


def test_rechercher_incidents_par_categorie(outils_initialises):
    resultat = rechercher_incidents_actifs("reseau")
    assert resultat["statut"] == "trouve"
    assert resultat["incidents"][0]["id"] == "INC-01"


def test_rechercher_incidents_par_service_affecte(outils_initialises):
    resultat = rechercher_incidents_actifs("tous")
    assert resultat["statut"] == "trouve"


def test_rechercher_incidents_sans_filtre(outils_initialises):
    assert rechercher_incidents_actifs("")["statut"] == "trouve"


def test_rechercher_incidents_aucun_resultat(outils_initialises):
    assert rechercher_incidents_actifs("imprimantes")["statut"] == "aucun_resultat"


def test_registry_couvre_exactement_les_8_outils():
    assert set(TOOL_REGISTRY) == {o["name"] for o in OUTILS}


# --- Outils d'action (AGT-3) ------------------------------------------------


def test_creer_ticket_retourne_un_id(outils_initialises):
    resultat = creer_ticket("mon écran ne s'allume plus", "materiel", "haute")
    assert resultat["statut"] == "succes"
    ticket = resultat["ticket"]
    assert ticket["id"].startswith("TK-")
    assert ticket["statut"] == "ouvert"


def test_ids_de_tickets_uniques(outils_initialises):
    premier = creer_ticket("pb 1", "autre", "basse")["ticket"]["id"]
    second = creer_ticket("pb 2", "autre", "basse")["ticket"]["id"]
    assert premier != second


def test_affecter_ticket(outils_initialises):
    identifiant = creer_ticket("pb", "logiciels", "moyenne")["ticket"]["id"]
    resultat = affecter_ticket(identifiant, "applications_metier")
    assert resultat["statut"] == "succes"
    assert resultat["ticket"]["equipe"] == "applications_metier"


def test_mettre_a_jour_ticket(outils_initialises):
    identifiant = creer_ticket("pb", "logiciels", "moyenne")["ticket"]["id"]
    resultat = mettre_a_jour_ticket(identifiant, {"statut": "en_cours"})
    assert resultat["ticket"]["statut"] == "en_cours"


def test_escalader_vers_technicien(outils_initialises):
    identifiant = creer_ticket("pb urgent", "reseau", "critique")["ticket"]["id"]
    resultat = escalader_vers_technicien(identifiant, "infrastructure_reseau", "incident global")
    assert resultat["statut"] == "succes"
    assert resultat["ticket"]["statut"] == "escalade"
    assert resultat["ticket"]["raison_escalade"] == "incident global"


def test_action_sur_ticket_inexistant_leve_une_erreur(outils_initialises):
    with pytest.raises(ValueError):
        affecter_ticket("TK-9999", "support_niveau_1")


# --- Déclaration Gemini (AGT-1) ---------------------------------------------

# --- Validation et exécution (AGT-4) ----------------------------------------


def test_valider_parametres_complets():
    assert valider_parametres("rechercher_utilisateur", {"identifiant": "U-001"})


def test_valider_parametres_incomplets():
    assert not valider_parametres("rechercher_utilisateur", {})


def test_valider_parametres_outil_inconnu():
    assert not valider_parametres("outil_inconnu", {})


def test_executer_consultation_avec_succes(outils_initialises):
    resultat = executer_outil("rechercher_utilisateur", {"identifiant": "U-001"}, "trace-test")
    assert resultat["statut"] == "succes"
    assert resultat["resultat"]["statut"] == "trouve"


def test_executer_parametres_manquants(outils_initialises):
    resultat = executer_outil("rechercher_utilisateur", {}, "trace-test")
    assert resultat["statut"] == "erreur"
    assert "manquants" in resultat["message"]


def test_executer_outil_inconnu(outils_initialises):
    resultat = executer_outil("supprimer_utilisateur", {}, "trace-test")
    assert resultat["statut"] == "erreur"


def test_executer_outil_sensible_bloque_avant_execution(outils_initialises):
    """Un outil sensible ne doit JAMAIS être exécuté sans validation humaine :
    `attente_validation_humaine` remplace le résultat, et aucun ticket ne doit
    être créé/modifié dans le registre."""
    avant = len(_tickets_courants)
    resultat = executer_outil(
        "mettre_a_jour_ticket",
        {"ticket_id": "TK-0001", "champs": {"statut": "ferme"}},
        "trace-test",
    )
    assert resultat["statut"] == "attente_validation_humaine"
    assert resultat["outil"] == "mettre_a_jour_ticket"
    assert len(_tickets_courants) == avant


def test_executer_erreur_d_outil_capturee(outils_initialises):
    """Une exception interne (ticket inexistant) doit être traduite en statut
    `erreur` exploitable par l'agent, jamais propagée."""
    resultat = executer_outil(
        "affecter_ticket",
        {"ticket_id": "TK-9999", "equipe": "support"},
        "trace-test",
    )
    assert resultat["statut"] == "erreur"
    assert "introuvable" in resultat["message"]


def test_executer_action_avec_succes(outils_initialises):
    resultat = executer_outil(
        "creer_ticket",
        {"description": "pb", "categorie": "autre", "priorite": "basse"},
        "trace-test",
    )
    assert resultat["statut"] == "succes"
    assert resultat["resultat"]["ticket"]["id"].startswith("TK-")


def test_log_appel_branche_et_appele(outils_initialises):
    """OBS-1 branchera `log_tool_call` ici : vérifier le contrat du hook."""
    appels = []

    def faux_log(trace_id, nom, params, resultat, statut, latence_ms):
        appels.append((trace_id, nom, statut))

    set_log_appel(faux_log)
    try:
        executer_outil("verifier_etat_service", {"service": "reseau"}, "trace-1")
    finally:
        set_log_appel(None)
    assert appels == [("trace-1", "verifier_etat_service", "succes")]
