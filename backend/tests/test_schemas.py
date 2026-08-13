"""Le schéma de sortie est le contrat central du projet (§5.3 du sujet).

Ces tests verrouillent ce contrat : si quelqu'un renomme un champ ou relâche
une contrainte pendant le hackathon, l'échec est immédiat et localisé, plutôt
que découvert pendant la démo.
"""

import pytest
from pydantic import ValidationError

from src.schemas import Classification, DiagnosticInfo, TicketDecision, TicketReponse


def decision_valide(**surcharges) -> dict:
    base = {
        "resume": "L'imprimante du 2e étage n'imprime plus.",
        "categorie": "imprimantes",
        "priorite": "moyenne",
        "equipe": "support_niveau_1",
        "confiance": 0.8,
        "informations_manquantes": [],
        "diagnostic": "File d'impression bloquée.",
        "etapes_resolution": ["Redémarrer le spouleur"],
        "sources": ["KB-IMP-01"],
        "outils_utilises": ["consulter_equipement"],
        "action": "resolution",
        "validation_humaine_requise": False,
    }
    return {**base, **surcharges}


def test_decision_complete_est_acceptee():
    decision = TicketDecision(**decision_valide())
    assert decision.action == "resolution"
    assert decision.sources == ["KB-IMP-01"]


def test_resume_est_obligatoire():
    """Le §3.5 du sujet exige un résumé du problème dans la sortie."""
    champs = decision_valide()
    del champs["resume"]
    with pytest.raises(ValidationError):
        TicketDecision(**champs)


@pytest.mark.parametrize("valeur", [-0.1, 1.5])
def test_confiance_hors_bornes_est_refusee(valeur):
    with pytest.raises(ValidationError):
        TicketDecision(**decision_valide(confiance=valeur))


def test_action_hors_enumeration_est_refusee():
    with pytest.raises(ValidationError):
        TicketDecision(**decision_valide(action="peut_etre"))


def test_trace_id_absent_de_la_decision():
    """trace_id est une métadonnée de routage : il vit dans l'enveloppe,
    pas dans la décision métier attendue par le sujet."""
    assert "trace_id" not in TicketDecision.model_fields
    assert "trace_id" in TicketReponse.model_fields


def test_enveloppe_expose_decision_et_trace():
    reponse = TicketReponse(trace_id="abc-123", decision=TicketDecision(**decision_valide()))
    charge_utile = reponse.model_dump()
    assert charge_utile["trace_id"] == "abc-123"
    assert charge_utile["decision"]["categorie"] == "imprimantes"


def test_classification_refuse_categorie_inconnue():
    with pytest.raises(ValidationError):
        Classification(
            categorie="plomberie", priorite="basse", equipe="x", justification="y"
        )


def test_diagnostic_accepte_champs_absents():
    """Un ticket vague ne remplit presque rien : seuls les champs vraiment
    manquants doivent être listés, le reste doit rester optionnel."""
    diag = DiagnosticInfo(informations_manquantes=["equipement", "moment_apparition"])
    assert diag.utilisateur is None
    assert len(diag.informations_manquantes) == 2
