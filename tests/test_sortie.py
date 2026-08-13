"""Tests de la sortie structurée (OUT-2/OUT-3).

La stratégie de retry est testée sans réseau : `prompt_fn` est simulé, on
vérifie la mécanique (nombre d'essais, transmission de l'erreur au 2e essai,
échec propre) et la validité constante de `reponse_erreur_controlee`.
"""

import pytest

from src.schemas import TicketDecision
from src.sortie import generer_avec_retry, reponse_erreur_controlee


def _brut_valide() -> dict:
    return {
        "resume": "Imprimante en panne.",
        "categorie": "imprimantes",
        "priorite": "moyenne",
        "equipe": "support_materiel",
        "confiance": 0.8,
        "informations_manquantes": [],
        "diagnostic": "File d'impression bloquée.",
        "etapes_resolution": ["Redémarrer le spouleur"],
        "sources": ["KB-IMP-01"],
        "outils_utilises": [],
        "action": "resolution",
        "validation_humaine_requise": False,
    }


def test_succes_des_le_premier_essai():
    """Sortie conforme : un seul appel, résultat retourné tel quel."""
    appels = []

    def prompt_fn(erreur_precedente=None):
        appels.append(erreur_precedente)
        return _brut_valide()

    resultat = generer_avec_retry(prompt_fn, TicketDecision)
    assert isinstance(resultat, TicketDecision)
    assert len(appels) == 1
    assert appels[0] is None


def test_echec_puis_succes_au_second_essai():
    """1er essai non conforme → 2e essai avec l'erreur transmise au prompt_fn."""
    appels = []

    def prompt_fn(erreur_precedente=None):
        appels.append(erreur_precedente)
        if erreur_precedente is None:
            brut = _brut_valide()
            brut["action"] = "peut_etre"  # invalide : hors énumération
            return brut
        return _brut_valide()

    resultat = generer_avec_retry(prompt_fn, TicketDecision)
    assert isinstance(resultat, TicketDecision)
    assert len(appels) == 2
    assert appels[1] is not None
    assert "peut_etre" in str(appels[1])


def test_echec_persistant_leve_une_erreur():
    """Deux échecs : RuntimeError explicite — jamais de sortie non conforme
    silencieuse ni de valeur partielle."""
    appels = []

    def prompt_fn(erreur_precedente=None):
        appels.append(erreur_precedente)
        brut = _brut_valide()
        brut.pop("resume")  # champ obligatoire manquant
        return brut

    with pytest.raises(RuntimeError, match="2 essais"):
        generer_avec_retry(prompt_fn, TicketDecision)
    assert len(appels) == 2


def test_max_essais_personnalisable():
    appels = []

    def prompt_fn(erreur_precedente=None):
        appels.append(erreur_precedente)
        brut = _brut_valide()
        brut.pop("resume")
        return brut

    with pytest.raises(RuntimeError, match="3 essais"):
        generer_avec_retry(prompt_fn, TicketDecision, max_essais=3)
    assert len(appels) == 3


def test_reponse_erreur_controlee_toujours_valide():
    decision = reponse_erreur_controlee("mon imprimante ne marche plus", "Timeout API Gemini")
    assert isinstance(decision, TicketDecision)  # valide par construction
    assert decision.action == "escalade"
    assert decision.validation_humaine_requise is True
    assert decision.confiance == 0.0
    assert "Timeout API Gemini" in decision.diagnostic


def test_reponse_erreur_controlee_description_vide():
    decision = reponse_erreur_controlee("", "Quota dépassé")
    assert decision.resume  # jamais vide, même sans description


def test_reponse_erreur_controlee_tronque_la_description():
    decision = reponse_erreur_controlee("x" * 500, "pb")
    assert len(decision.resume) <= 200


def test_validation_error_est_bien_attrapee_par_le_retry():
    """Le retry ne doit réagir qu'aux ValidationError : les autres exceptions
    (ex. réseau) remontent immédiatement, ce n'est pas un problème de schéma."""

    def prompt_fn(erreur_precedente=None):
        raise TimeoutError("réseau en panne")

    with pytest.raises(TimeoutError):
        generer_avec_retry(prompt_fn, TicketDecision)