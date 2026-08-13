"""Tests du diagnostic (DIAG-1/DIAG-2/DIAG-3).

Remplace l'ancien `src/test_diagno.py` : un script manuel (print/assert au
niveau module, pas de fonction test_*), placé hors de `tests/` donc jamais
exécuté par pytest (`testpaths = ["tests"]`), et qui appelait le vrai LLM à
chaque lecture du fichier. `extraire_diagnostic` est ici simulé (monkeypatch
de `llm_call`) pour tester le câblage sans consommer de quota ; les
assertions sur `generer_questions` reprennent celles du script d'origine.
"""

from src.diagnostic import extraire_diagnostic, generer_questions
from src.schemas import DiagnosticInfo


def test_extraire_diagnostic_appelle_llm_avec_le_bon_schema(monkeypatch):
    recu = {}

    def faux_llm_call(prompt_systeme, prompt_utilisateur, response_schema=None):
        recu["prompt_utilisateur"] = prompt_utilisateur
        recu["response_schema"] = response_schema
        return DiagnosticInfo(informations_manquantes=["equipement", "moment_apparition"])

    monkeypatch.setattr("src.diagnostic.llm_call", faux_llm_call)
    resultat = extraire_diagnostic("Ça ne marche plus.")

    assert isinstance(resultat, DiagnosticInfo)
    assert recu["response_schema"] is DiagnosticInfo
    assert recu["prompt_utilisateur"] == "Ça ne marche plus."


def test_generer_questions_limite_a_deux():
    questions = generer_questions(["utilisateur", "equipement", "moment_apparition", "impact"])
    assert len(questions) <= 2


def test_generer_questions_priorise_les_champs_les_plus_utiles():
    """application (priorité 10) doit primer sur utilisateur (priorité 3)."""
    questions = generer_questions(["utilisateur", "application"])
    assert questions[0] == "Quelle application ou quel service est concerné ?"


def test_generer_questions_champ_inconnu_a_une_question_generique():
    assert generer_questions(["champ_bizarre"]) == ["Pouvez-vous préciser : champ_bizarre ?"]


def test_generer_questions_liste_vide():
    assert generer_questions([]) == []
