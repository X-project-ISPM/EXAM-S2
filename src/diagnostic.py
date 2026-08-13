"""Diagnostic du ticket (§3.2 du sujet, DIAG-1/DIAG-2/DIAG-3).

Complète la classification : extrait les informations déjà présentes dans le
ticket et identifie les manques avant de proposer une solution (scénario 3 —
demande incomplète).
"""

from src.llm_client import llm_call
from src.schemas import DiagnosticInfo

PROMPT_DIAGNOSTIC = """Extrait les informations disponibles dans ce ticket parmi :
utilisateur, equipement, application, symptomes, moment_apparition, impact,
manipulations_effectuees.

Liste dans informations_manquantes uniquement les champs qui sont à la fois absents
du texte ET nécessaires pour permettre un diagnostic fiable pour ce type de problème
(ex. pour un problème réseau, l'equipement et le moment_apparition sont importants ;
pour un mot de passe oublié, ils le sont moins)."""


def extraire_diagnostic(description: str) -> DiagnosticInfo:
    resultat = llm_call(PROMPT_DIAGNOSTIC, description, response_schema=DiagnosticInfo)
    assert isinstance(resultat, DiagnosticInfo)  # garanti par response_schema
    return resultat


# --- Questions ciblées (DIAG-3) ----------------------------------------------

PRIORITE_CHAMPS = {
    "application": 10,
    "symptomes": 10,
    "equipement": 9,
    "moment_apparition": 7,
    "impact": 6,
    "manipulations_effectuees": 5,
    "utilisateur": 3,
}


def generer_questions(infos_manquantes: list[str]) -> list[str]:
    """
    Transforme une liste de champs manquants en questions ciblées.
    Sélectionne les 2 champs les plus prioritaires (via PRIORITE_CHAMPS),
    plutôt que les 2 premiers dans l'ordre renvoyé par le LLM — l'ordre du
    LLM n'a aucune garantie de pertinence.
    """
    questions_types = {
        "equipement": "Quel équipement est concerné (numéro d'inventaire ou description) ?",
        "moment_apparition": "Depuis quand rencontrez-vous ce problème ?",
        "manipulations_effectuees": (
            "Avez-vous déjà essayé une manipulation pour résoudre ce problème ?"
        ),
        "utilisateur": "Pour quel utilisateur ou compte rencontrez-vous ce problème ?",
        "application": "Quelle application ou quel service est concerné ?",
        "impact": "Quel est l'impact sur votre activité (bloquant, gênant, mineur) ?",
        "symptomes": (
            "Pouvez-vous décrire plus précisément ce qui se passe "
            "(message d'erreur, comportement observé) ?"
        ),
    }

    champs_tries = sorted(infos_manquantes, key=lambda c: PRIORITE_CHAMPS.get(c, 0), reverse=True)

    return [questions_types.get(champ, f"Pouvez-vous préciser : {champ} ?")
            for champ in champs_tries[:2]]
