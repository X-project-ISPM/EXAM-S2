"""Tests de la boucle agent (AGT-5/6).

Le LLM est simulé (monkeypatch de `llm_call_with_tools`) : on teste la
mécanique de la boucle — exécution des outils, renvoi des résultats au modèle,
blocage des actions sensibles, limite d'itérations — sans consommer de quota.
"""

import pytest
from google.genai import types

from src.agent import (
    charger_action_en_attente,
    executer_action_approuvee,
    rejeter_action_en_attente,
    run_agent,
)
from src.llm_client import LLMError
from src.schemas import Classification, DiagnosticInfo, TicketDecision

CLASSIFICATION = Classification(
    categorie="imprimantes",
    priorite="moyenne",
    equipe="support_materiel",
    confiance=0.9,
    justification="imprimante injoignable",
)

DIAGNOSTIC = DiagnosticInfo(
    equipement="IMP-001",
    symptomes="n'imprime plus",
    informations_manquantes=[],
)

CONTEXTE = [
    {"contenu": "Redémarrer l'imprimante puis vérifier la file d'impression.",
     "source_id": "KB-IMP-01", "titre": "Imprimante muette", "distance": 0.2}
]


def _reponse_finale(parsed=None, texte=""):
    """Objet simulant une GenerateResponse sans appel d'outil."""
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=texte)])
            )
        ],
        parsed=parsed,
    )


def _reponse_avec_appel(nom: str, args: dict):
    """Objet simulant une GenerateResponse qui appelle un outil."""
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(name=nom, args=args)
                        )
                    ],
                )
            )
        ]
    )


@pytest.fixture
def decision_finale():
    return TicketDecision(
        resume="Imprimante IMP-001 injoignable",
        categorie="imprimantes",
        priorite="moyenne",
        equipe="support_materiel",
        confiance=0.85,
        informations_manquantes=[],
        diagnostic="L'imprimante ne répond plus.",
        etapes_resolution=["Redémarrer l'imprimante.", "Vérifier la file."],
        sources=["KB-IMP-01"],
        outils_utilises=[],
        action="resolution",
        validation_humaine_requise=False,
    )


def _monkeypatcher(monkeypatch, reponses):
    """Remplace llm_call_with_tools par une file de réponses, et retourne
    l'historique des messages reçus pour vérification."""
    recus = []

    def faux_appel(messages, prompt_systeme, tools, response_schema=None):
        recus.append((messages, prompt_systeme, tools, response_schema))
        return reponses.pop(0)

    monkeypatch.setattr("src.agent.llm_call_with_tools", faux_appel)
    return recus


def test_reponse_finale_directe(monkeypatch, decision_finale):
    _monkeypatcher(monkeypatch, [_reponse_finale(parsed=decision_finale)])
    decision = run_agent("imprimante en panne", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t1")
    assert decision.action == "resolution"
    assert decision.sources == ["KB-IMP-01"]
    assert decision.outils_utilises == []


def test_appel_outil_puis_reponse_finale(monkeypatch, decision_finale):
    """Le modèle appelle verifier_etat_service, reçoit le résultat, puis
    produit sa réponse finale : l'historique doit contenir le
    FunctionResponse, et la décision doit lister l'outil utilisé."""
    from src.models import BaseDeDonnees, Service
    from src.tools import initialiser_donnees

    initialiser_donnees(BaseDeDonnees(
        utilisateurs=[], equipements=[], incidents_actifs=[], kb=[],
        tickets_historique=[], services=[Service(nom="impression", statut="degrade")],
    ))
    recus = _monkeypatcher(
        monkeypatch,
        [
            _reponse_avec_appel("verifier_etat_service", {"service": "impression"}),
            _reponse_finale(parsed=decision_finale),
        ],
    )
    decision = run_agent("imprimante en panne", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t2")

    assert decision.outils_utilises == ["verifier_etat_service"]
    dernier = recus[-1][0][-1]  # dernier message envoyé au modèle
    assert dernier.role == "user"
    reponse = dernier.parts[0].function_response
    assert reponse.name == "verifier_etat_service"
    assert reponse.response["statut"] == "succes"


def test_action_sensible_bloque_et_sauvegarde(monkeypatch):
    """Le modèle tente de mettre à jour un ticket : executer_outil répond
    attente_validation_humaine, la boucle s'arrête en escalade, et l'action
    est conservée pour /tickets/valider (ORCH-2)."""
    from src.models import BaseDeDonnees
    from src.tools import creer_ticket, initialiser_donnees

    initialiser_donnees(BaseDeDonnees(
        utilisateurs=[], equipements=[], incidents_actifs=[], kb=[],
        tickets_historique=[], services=[],
    ))
    identifiant = creer_ticket("pb", "autre", "basse")["ticket"]["id"]
    _monkeypatcher(
        monkeypatch,
        [
            _reponse_avec_appel(
                "mettre_a_jour_ticket",
                {"ticket_id": identifiant, "champs": {"statut": "ferme"}},
            ),
        ],
    )
    decision = run_agent("ticket à fermer", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t3")

    assert decision.action == "escalade"
    assert decision.validation_humaine_requise is True
    assert "validation humaine" in decision.diagnostic.lower()
    assert decision.outils_utilises == ["mettre_a_jour_ticket"]

    action = charger_action_en_attente("t3")
    assert action is not None
    assert action["outil"] == "mettre_a_jour_ticket"

    # L'exécution réelle n'a lieu qu'après approbation (AGT-6 / ORCH-2).
    resultat = executer_action_approuvee("t3")
    assert resultat["statut"] == "succes"
    assert charger_action_en_attente("t3") is None


def test_rejet_action_en_attente(monkeypatch):
    _monkeypatcher(
        monkeypatch,
        [_reponse_avec_appel("escalader_vers_technicien",
                             {"ticket_id": "TK-0001", "equipe": "reseau", "raison": "urgent"})],
    )
    run_agent("urgent", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t4")
    assert charger_action_en_attente("t4") is not None
    rejeter_action_en_attente("t4")
    assert charger_action_en_attente("t4") is None
    with pytest.raises(KeyError):
        executer_action_approuvee("t4")


def test_erreur_d_outil_retournee_au_modele(monkeypatch, decision_finale):
    """Une erreur d'outil (ticket inexistant) est un résultat exploitable par
    le modèle, pas un crash : la boucle continue et le modèle peut répondre."""
    recus = _monkeypatcher(
        monkeypatch,
        [
            _reponse_avec_appel("affecter_ticket", {"ticket_id": "TK-9999", "equipe": "x"}),
            _reponse_finale(parsed=decision_finale),
        ],
    )
    decision = run_agent("pb", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t5")
    assert decision.action == "resolution"
    reponse = recus[-1][0][-1].parts[0].function_response
    assert reponse.response["statut"] == "erreur"


def test_limite_d_iterations_atteinte(monkeypatch):
    """Le modèle appelle un outil à chaque itération : la boucle doit
    s'arrêter à agent_max_iterations et produire une escalade propre, jamais
    une erreur nue."""
    from src.models import BaseDeDonnees, Service
    from src.tools import initialiser_donnees

    initialiser_donnees(BaseDeDonnees(
        utilisateurs=[], equipements=[], incidents_actifs=[], kb=[],
        tickets_historique=[], services=[Service(nom="x", statut="operationnel")],
    ))
    appel = _reponse_avec_appel("verifier_etat_service", {"service": "x"})
    _monkeypatcher(monkeypatch, [appel] * 5)
    decision = run_agent("boucle", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t6")

    assert decision.action == "escalade"
    assert decision.validation_humaine_requise is True
    assert "itérations" in decision.diagnostic.lower()
    assert len(decision.outils_utilises) == 5


def test_reponse_finale_non_conforme_leve_llm_error(monkeypatch):
    """Sortie du modèle ni outil ni JSON valide : LLMError, que
    l'orchestrateur dégradera (ORCH-3)."""
    _monkeypatcher(monkeypatch, [_reponse_finale(texte="je ne sais pas")])
    with pytest.raises(LLMError):
        run_agent("pb", CLASSIFICATION, DIAGNOSTIC, CONTEXTE, "t7")


def test_contexte_vide_accepte(monkeypatch, decision_finale):
    """Le RAG des autres membres peut être indisponible : la boucle doit
    tourner sans contexte (cas "pas de document")."""
    _monkeypatcher(monkeypatch, [_reponse_finale(parsed=decision_finale)])
    decision = run_agent("pb", CLASSIFICATION, DIAGNOSTIC, None, "t8")
    assert decision.action == "resolution"


# --- Appel réel (consomme du quota, marqué reseau) ---------------------------


@pytest.mark.reseau
def test_agent_reel_bout_en_bout():
    """Un tour complet avec le vrai LLM : le modèle doit soit résoudre en
    citant la KB, soit escalader proprement — jamais lever d'exception."""
    decision = run_agent(
        "Mon imprimante du 2e étage n'imprime plus depuis ce matin.",
        CLASSIFICATION,
        DIAGNOSTIC,
        CONTEXTE,
        "trace-reel",
    )
    assert isinstance(decision, TicketDecision)
    assert decision.action in {"resolution", "demande_information", "escalade"}