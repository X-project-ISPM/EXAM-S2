"""Tests du diagnostic (§3.2 du sujet, scénario 3 obligatoire).

La détermination de ce qui manque et la formulation des questions sont
déterministes : elles se testent sans réseau, et doivent rester stables même
quand le modèle varie.
"""

import pytest

from src.diagnostic import (
    CHAMPS_REQUIS_PAR_CATEGORIE,
    NB_QUESTIONS_MAX,
    QUESTIONS_TYPES,
    champs_requis,
    diagnostic_suffisant,
    extraire_diagnostic,
    generer_questions,
)
from src.schemas import CATEGORIES, DiagnosticInfo, ExtractionDiagnostic

# --- Champs requis ----------------------------------------------------------


def test_toutes_les_categories_ont_des_champs_requis():
    """Une catégorie oubliée retomberait sur le minimum commun sans que
    personne ne s'en aperçoive."""
    assert set(CHAMPS_REQUIS_PAR_CATEGORIE) == set(CATEGORIES)


def test_les_champs_requis_existent_dans_le_schema():
    champs_du_schema = set(ExtractionDiagnostic.model_fields)
    for categorie, requis in CHAMPS_REQUIS_PAR_CATEGORIE.items():
        assert set(requis) <= champs_du_schema, f"champ inconnu pour {categorie}"


def test_chaque_champ_requis_a_une_question():
    """Sans question associée, l'utilisateur recevrait le libellé technique
    du champ à la place d'une vraie question."""
    for requis in CHAMPS_REQUIS_PAR_CATEGORIE.values():
        for champ in requis:
            assert champ in QUESTIONS_TYPES


def test_une_categorie_inconnue_retombe_sur_le_minimum():
    assert champs_requis("categorie_qui_nexiste_pas") == ("symptomes",)
    assert champs_requis(None) == ("symptomes",)


def test_un_mot_de_passe_oublie_ne_reclame_pas_d_equipement():
    """Réclamer un numéro d'inventaire pour un mot de passe oublié ferait
    perdre un aller-retour à l'utilisateur pour rien."""
    assert "equipement" not in champs_requis("comptes_authentification")


def test_un_incident_de_securite_reclame_les_manipulations():
    """La procédure KB-SEC-01 demande explicitement si la pièce jointe a été
    ouverte : la réponse change toute la conduite à tenir."""
    assert "manipulations_effectuees" in champs_requis("cybersecurite")


# --- Détection des champs absents -------------------------------------------


@pytest.fixture
def extraction_simulee(monkeypatch):
    def _configurer(**champs):
        extraction = ExtractionDiagnostic(**champs)
        monkeypatch.setattr("src.diagnostic.llm_call", lambda *a, **k: extraction)

    return _configurer


def test_ticket_complet_ne_manque_de_rien(extraction_simulee):
    extraction_simulee(equipement="poste PC-042", symptomes="écran noir")
    diagnostic = extraire_diagnostic("mon poste PC-042 a l'écran noir", categorie="materiel")

    assert diagnostic.informations_manquantes == []
    assert diagnostic_suffisant(diagnostic)


def test_ticket_vague_liste_les_champs_manquants(extraction_simulee):
    extraction_simulee()
    diagnostic = extraire_diagnostic("ça ne marche plus", categorie="materiel")

    assert set(diagnostic.informations_manquantes) == {"equipement", "symptomes"}
    assert not diagnostic_suffisant(diagnostic)


def test_seuls_les_champs_requis_sont_reclames(extraction_simulee):
    """`impact` est vide mais n'est pas requis pour du matériel : le réclamer
    allongerait l'échange sans améliorer le diagnostic."""
    extraction_simulee(equipement="PC-042", symptomes="écran noir", impact=None)
    diagnostic = extraire_diagnostic("...", categorie="materiel")

    assert diagnostic.informations_manquantes == []


@pytest.mark.parametrize(
    "valeur",
    ["Ça ne marche plus.", "ca ne marche plus", "ÇA NE MARCHE PLUS !"],
)
def test_un_champ_qui_recopie_le_ticket_compte_comme_absent(extraction_simulee, valeur):
    """Le modèle renvoie parfois le ticket tel quel comme symptôme. Le champ
    paraîtrait renseigné, aucune question ne serait posée, et le ticket le
    plus vague qui soit passerait pour complet — le scénario 3 ne se
    déclencherait jamais."""
    extraction_simulee(symptomes=valeur)
    diagnostic = extraire_diagnostic("Ça ne marche plus.", categorie="autre")

    assert diagnostic.informations_manquantes == ["symptomes"]
    assert not diagnostic_suffisant(diagnostic)


def test_un_champ_qui_extrait_une_partie_du_ticket_est_conserve(extraction_simulee):
    """Contrepartie : une extraction partielle est une vraie information et
    ne doit pas être écartée."""
    extraction_simulee(symptomes="ne démarre plus", equipement="ordinateur")
    diagnostic = extraire_diagnostic(
        "Mon ordinateur ne démarre plus depuis ce matin.", categorie="materiel"
    )

    assert diagnostic.informations_manquantes == []


@pytest.mark.parametrize("valeur", ["", "   ", "non précisé", "inconnu", "N/A", "-"])
def test_les_valeurs_creuses_comptent_comme_absentes(extraction_simulee, valeur):
    """Le modèle renvoie parfois « non précisé » au lieu d'un null ; sans
    garde, le champ passerait pour renseigné et la question ne serait jamais
    posée."""
    extraction_simulee(equipement=valeur, symptomes="écran noir")
    diagnostic = extraire_diagnostic("...", categorie="materiel")

    assert "equipement" in diagnostic.informations_manquantes


def test_la_categorie_change_ce_qui_est_reclame(extraction_simulee):
    extraction_simulee(utilisateur="Jean Dupont")

    materiel = extraire_diagnostic("...", categorie="materiel")
    comptes = extraire_diagnostic("...", categorie="comptes_authentification")

    # L'utilisateur est renseigné : jamais réclamé, quelle que soit la catégorie.
    assert "utilisateur" not in comptes.informations_manquantes
    assert "utilisateur" not in materiel.informations_manquantes
    # Mais ce qui est réclamé diffère bien selon la catégorie.
    assert set(materiel.informations_manquantes) == {"equipement", "symptomes"}
    assert set(comptes.informations_manquantes) == {"symptomes"}


# --- Questions ciblées ------------------------------------------------------


def test_aucune_question_si_rien_ne_manque():
    assert generer_questions([]) == []


def test_jamais_plus_de_deux_questions():
    toutes = list(QUESTIONS_TYPES)
    assert len(generer_questions(toutes)) <= NB_QUESTIONS_MAX


def test_les_questions_les_plus_utiles_sont_retenues():
    """L'ordre des champs manquants suit la déclaration du schéma, pas leur
    importance : sans tri, on demanderait le nom de l'utilisateur avant les
    symptômes."""
    questions = generer_questions(["utilisateur", "symptomes"])
    assert questions[0] == QUESTIONS_TYPES["symptomes"]


def test_un_champ_inattendu_produit_une_question_lisible():
    questions = generer_questions(["champ_exotique"])
    assert questions == ["Pouvez-vous préciser : champ_exotique ?"]


def test_la_question_de_securite_cible_les_gestes_a_risque():
    """Sans reformulation par catégorie, on demanderait « avez-vous tenté
    quelque chose ? » à quelqu'un qui vient peut-être de saisir ses
    identifiants sur une page de phishing."""
    generique = generer_questions(["manipulations_effectuees"])[0]
    securite = generer_questions(["manipulations_effectuees"], categorie="cybersecurite")[0]

    assert generique != securite
    assert "pièce jointe" in securite


def test_les_questions_specifiques_referencent_des_champs_connus():
    """Une clé mal orthographiée dans la table par catégorie serait ignorée
    en silence, et la question générique reprendrait sa place."""
    from src.diagnostic import QUESTIONS_PAR_CATEGORIE

    for categorie, questions in QUESTIONS_PAR_CATEGORIE.items():
        assert categorie in CATEGORIES
        assert set(questions) <= set(QUESTIONS_TYPES)


def test_les_questions_sont_des_phrases_interrogatives():
    for question in QUESTIONS_TYPES.values():
        assert question.rstrip().endswith("?")


# --- Scénario 3 bout en bout ------------------------------------------------


@pytest.mark.reseau
def test_scenario_3_ticket_vague_declenche_des_questions():
    """« Ça ne marche plus » est l'exemple type du scénario 3 : le système
    doit reconnaître qu'il ne peut pas diagnostiquer et demander des
    précisions."""
    diagnostic = extraire_diagnostic("Ça ne marche plus.", categorie="autre")

    assert not diagnostic_suffisant(diagnostic)
    questions = generer_questions(diagnostic.informations_manquantes)
    assert 1 <= len(questions) <= NB_QUESTIONS_MAX


@pytest.mark.reseau
def test_extraction_ne_remplit_pas_les_champs_absents():
    """Garde-fou central : un ticket qui ne dit rien ne doit rien produire.

    C'est le mode de défaillance le plus coûteux — un champ inventé passe
    pour renseigné, la question n'est jamais posée, et le diagnostic se fait
    sur une base fausse.
    """
    diagnostic = extraire_diagnostic("Ça ne marche plus.", categorie="materiel")

    assert isinstance(diagnostic, DiagnosticInfo)
    assert diagnostic.equipement is None
    assert diagnostic.symptomes is None
    assert diagnostic.moment_apparition is None
    assert set(diagnostic.informations_manquantes) == {"equipement", "symptomes"}


@pytest.mark.reseau
def test_extraction_capte_ce_qui_est_reellement_dit():
    """Contrepartie : une indication de temps présente doit être captée,
    sinon on repose une question déjà répondue."""
    diagnostic = extraire_diagnostic(
        "Mon ordinateur ne démarre plus depuis ce matin.", categorie="materiel"
    )

    assert diagnostic.moment_apparition is not None
    assert diagnostic.symptomes is not None


@pytest.mark.reseau
def test_scenario_securite_pose_la_question_qui_compte():
    """KB-SEC-01 a besoin de savoir si la pièce jointe a été ouverte : la
    question générique « avez-vous tenté quelque chose ? » n'obtient pas
    cette information."""
    diagnostic = extraire_diagnostic(
        "J'ai reçu un courriel suspect avec une pièce jointe.", categorie="cybersecurite"
    )
    questions = generer_questions(diagnostic.informations_manquantes, categorie="cybersecurite")

    assert any("pièce jointe" in q or "identifiants" in q for q in questions)
