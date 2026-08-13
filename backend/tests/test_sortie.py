"""Tests de la sortie structurée (OUT-2/OUT-3).

La stratégie de retry est testée sans réseau : `prompt_fn` est simulé, on
vérifie la mécanique (nombre d'essais, transmission de l'erreur au 2e essai,
échec propre) et la validité constante de `reponse_erreur_controlee`.
"""

import pytest

from src.llm_client import LLMError, QuotaDepasseError, SchemaNonConforme
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


def test_schema_non_conforme_de_llm_call_declenche_bien_le_retry():
    """`prompt_fn` branché directement sur `llm_call(..., response_schema=...)`
    (l'usage réel prévu par ORCH-1) ne lève jamais `ValidationError` en cas de
    non-conformité : il lève `SchemaNonConforme`. Avant ce fix, cette
    exception traversait `generer_avec_retry` sans déclencher de régénération —
    le retry n'existait alors que sur le papier pour cet usage."""
    appels = []

    def prompt_fn(erreur_precedente=None):
        appels.append(erreur_precedente)
        if erreur_precedente is None:
            raise SchemaNonConforme("le modèle n'a pas produit de JSON conforme")
        return _brut_valide()

    resultat = generer_avec_retry(prompt_fn, TicketDecision)
    assert isinstance(resultat, TicketDecision)
    assert len(appels) == 2
    assert "JSON conforme" in str(appels[1])


def test_max_essais_zero_ne_retombe_pas_sur_la_valeur_par_defaut():
    """`0` est falsy en Python : `max_essais or config...` retombait
    silencieusement sur la valeur par défaut au lieu de zéro tentative."""
    with pytest.raises(RuntimeError, match="0 essais"):
        generer_avec_retry(
            lambda erreur_precedente=None: _brut_valide(), TicketDecision, max_essais=0
        )


def test_erreur_reseau_ou_quota_remonte_immediatement_pas_de_retry():
    """`LLMError`/`QuotaDepasseError` génériques (réseau, quota) ne sont pas
    des problèmes de schéma : ils doivent continuer à remonter tout de suite,
    sans consommer un essai de régénération inutile."""
    appels = []

    def prompt_fn(erreur_precedente=None):
        appels.append(erreur_precedente)
        raise QuotaDepasseError("quota Gemini dépassé")

    with pytest.raises(LLMError):
        generer_avec_retry(prompt_fn, TicketDecision)
    assert len(appels) == 1


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


def test_reponse_erreur_controlee_masque_les_secrets():
    """SEC-5 : un message d'erreur peut recopier un extrait brut de réponse
    LLM — potentiellement le ticket lui-même, secrets compris. Ni la
    description ni le message d'erreur ne doivent fuiter tels quels."""
    decision = reponse_erreur_controlee(
        "mon mot de passe : Ete2024! ne fonctionne plus",
        "Réponse brute : mot de passe : Ete2024!",
    )
    assert "Ete2024!" not in decision.resume
    assert "Ete2024!" not in decision.diagnostic
    assert "***" in decision.resume


def test_validation_error_est_bien_attrapee_par_le_retry():
    """Le retry ne doit réagir qu'aux ValidationError : les autres exceptions
    (ex. réseau) remontent immédiatement, ce n'est pas un problème de schéma."""

    def prompt_fn(erreur_precedente=None):
        raise TimeoutError("réseau en panne")

    with pytest.raises(TimeoutError):
        generer_avec_retry(prompt_fn, TicketDecision)