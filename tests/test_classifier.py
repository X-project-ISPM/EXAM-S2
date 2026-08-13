"""Tests du classifieur.

La partie déterministe (routage, filet de sécurité) est testée sans réseau :
c'est elle qui doit rester stable même quand le modèle varie.
"""

import pytest

from src.classifier import (
    EQUIPES_PAR_CATEGORIE,
    classify_ticket,
    detecter_indice_cybersecurite,
    router_vers_equipe,
)
from src.schemas import CATEGORIES, EQUIPES, AnalyseTicket, Classification

# --- Routage ----------------------------------------------------------------


def test_chaque_categorie_a_une_equipe():
    """Aucune catégorie ne doit tomber dans le routage par défaut sans qu'on
    l'ait décidé explicitement."""
    assert set(EQUIPES_PAR_CATEGORIE) == set(CATEGORIES)


def test_equipes_routees_font_partie_du_vocabulaire():
    assert set(EQUIPES_PAR_CATEGORIE.values()) <= set(EQUIPES)


def test_cybersecurite_va_a_la_securite():
    assert router_vers_equipe("cybersecurite") == "securite_si"


def test_categorie_inconnue_retombe_sur_le_niveau_1():
    assert router_vers_equipe("categorie_qui_nexiste_pas") == "support_niveau_1"


# --- Filet de sécurité ------------------------------------------------------


@pytest.mark.parametrize(
    "texte",
    [
        "j'ai reçu un courriel suspect",
        "un mail avec une pièce jointe étrange",
        "je crois que mon poste est compromis",
        "tentative de phishing sur ma boite",
        "il y a un ransomware sur le serveur",
        "mon ordinateur a un virus",
    ],
)
def test_indices_cybersecurite_detectes(texte):
    assert detecter_indice_cybersecurite(texte)


@pytest.mark.parametrize(
    "texte",
    [
        "j'ai oublié mon mot de passe",
        "l'imprimante ne répond plus",
        "mon écran est cassé",
        "je voudrais accéder au dossier partagé",
    ],
)
def test_tickets_ordinaires_ne_declenchent_pas_le_filet(texte):
    """Un filet trop large enverrait tout le support courant vers l'équipe
    sécurité et rendrait le signal inutile."""
    assert not detecter_indice_cybersecurite(texte)


@pytest.mark.parametrize(
    "texte",
    [
        "la nouvelle version de l'antivirus ralentit mon poste",
        "la nouvelle version de l'anti-virus ralentit mon poste",
        "mon logiciel anti-virus doit être mis à jour",
    ],
)
def test_mention_d_un_outil_de_securite_ne_declenche_pas_le_filet(texte):
    """Régression : le trait d'union de « anti-virus » crée une frontière de
    mot avant « virus ». Sans garde, une mise à jour d'antivirus partait en
    incident critique vers l'équipe sécurité."""
    assert not detecter_indice_cybersecurite(texte)


# --- Assemblage (LLM simulé) ------------------------------------------------


@pytest.fixture
def llm_simule(monkeypatch):
    """Remplace l'appel réseau pour tester la logique d'assemblage seule."""

    def _configurer(
        categorie: str,
        priorite: str = "moyenne",
        confiance: float = 0.9,
        incident_securite_avere: bool = False,
    ):
        def faux_appel(_systeme, _utilisateur, response_schema=None):
            return AnalyseTicket(
                categorie=categorie,
                priorite=priorite,
                confiance=confiance,
                incident_securite_avere=incident_securite_avere,
                justification="justification simulée",
            )

        monkeypatch.setattr("src.classifier.llm_call", faux_appel)

    return _configurer


def test_equipe_derivee_de_la_categorie(llm_simule):
    llm_simule("reseau")
    resultat = classify_ticket("le wifi ne marche plus")
    assert isinstance(resultat, Classification)
    assert resultat.equipe == "infrastructure_reseau"


def test_incident_securite_confirme_force_la_categorie(llm_simule):
    """Le modèle peut se contredire : signaler un incident de sécurité tout en
    classant ailleurs. Son adjudication explicite fait foi."""
    llm_simule("comptes_authentification", priorite="basse", incident_securite_avere=True)
    resultat = classify_ticket("j'ai reçu un courriel suspect qui demande mon mot de passe")

    assert resultat.categorie == "cybersecurite"
    assert resultat.equipe == "securite_si"
    assert resultat.priorite == "critique"


def test_filet_rattrape_quand_le_modele_ecarte_sans_conviction(llm_simule):
    """Signal lexical présent, le modèle écarte la piste sécurité mais avec une
    confiance basse : la précaution l'emporte (§6)."""
    llm_simule("comptes_authentification", priorite="basse", confiance=0.4)
    resultat = classify_ticket("j'ai reçu un courriel suspect qui demande mon mot de passe")

    assert resultat.categorie == "cybersecurite"
    assert resultat.priorite == "critique"
    assert "précaution" in resultat.justification.lower()


def test_modele_confiant_peut_ecarter_la_piste_securite(llm_simule):
    """Contrepartie : sans cela, « l'antivirus ralentit mon poste » finirait en
    incident critique. On sollicite le jugement du modèle, donc on l'utilise."""
    llm_simule("logiciels", priorite="moyenne", confiance=0.95, incident_securite_avere=False)
    resultat = classify_ticket("un virus a été détecté et supprimé par l'outil, tout va bien")

    assert resultat.categorie == "logiciels"
    assert resultat.equipe == "applications_metier"


def test_confiance_plafonnee_quand_une_regle_contredit_le_modele(llm_simule):
    """La confiance du modèle portait sur SA catégorie ; la reporter telle
    quelle sur une catégorie substituée surestimerait notre certitude et
    pourrait faire sauter la validation humaine en aval.

    Ici le modèle se contredit (incident de sécurité avéré, mais classé en
    comptes) : la catégorie est corrigée, donc la confiance doit retomber."""
    llm_simule(
        "comptes_authentification",
        priorite="basse",
        confiance=0.97,
        incident_securite_avere=True,
    )
    resultat = classify_ticket("j'ai reçu un courriel suspect qui demande mon mot de passe")

    assert resultat.categorie == "cybersecurite"
    assert resultat.confiance <= 0.5


def test_confiance_intacte_sans_requalification(llm_simule):
    llm_simule("reseau", confiance=0.93)
    assert classify_ticket("le wifi ne marche plus").confiance == pytest.approx(0.93)


def test_pas_de_reclassement_sans_indice(llm_simule):
    llm_simule("comptes_authentification", priorite="basse", confiance=0.4)
    resultat = classify_ticket("j'ai oublié mon mot de passe")
    assert resultat.categorie == "comptes_authentification"
    assert resultat.priorite == "basse"


def test_priorite_haute_preservee_lors_du_reclassement(llm_simule):
    """Le reclassement ne doit relever que les priorités sous-évaluées, pas
    écraser une priorité déjà jugée élevée."""
    llm_simule("logiciels", priorite="haute", incident_securite_avere=True)
    resultat = classify_ticket("un virus bloque mon application")
    assert resultat.priorite == "haute"


# --- Appel réel -------------------------------------------------------------


@pytest.mark.reseau
def test_classification_reelle_bout_en_bout():
    resultat = classify_ticket("Impossible d'accéder au serveur, toute l'équipe est bloquée.")
    assert resultat.categorie == "reseau"
    assert resultat.priorite == "critique"
    assert resultat.equipe == "infrastructure_reseau"
    assert 0.0 <= resultat.confiance <= 1.0
