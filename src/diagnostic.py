# src/diagnostic.py
from schemas import DiagnosticInfo
from llm_client import llm_call  # adapte l'import selon où se trouve ton wrapper SETUP-4

PROMPT_DIAGNOSTIC = """Extrait les informations disponibles dans ce ticket parmi :
utilisateur, equipement, application, symptomes, moment_apparition, impact,
manipulations_effectuees.

Liste dans informations_manquantes uniquement les champs qui sont à la fois absents
du texte ET nécessaires pour permettre un diagnostic fiable pour ce type de problème
(ex. pour un problème réseau, l'equipement et le moment_apparition sont importants ;
pour un mot de passe oublié, ils le sont moins)."""

def extraire_diagnostic(description: str) -> DiagnosticInfo:
    return llm_call(PROMPT_DIAGNOSTIC, description, response_schema=DiagnosticInfo)