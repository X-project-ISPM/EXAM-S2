# tests/test_diagnostic_manuel.py
from diagnostic import extraire_diagnostic, generer_questions

CAS_TEST = [
    "Ça ne marche plus.",
    "J'ai un problème avec mon compte.",
    "Impossible de me connecter, aide.",
]

for description in CAS_TEST:
    info = extraire_diagnostic(description)
    questions = generer_questions(info.informations_manquantes)

    print(f"\n--- Ticket: {description!r} ---")
    print("DiagnosticInfo:", info)
    print("Manquantes:", info.informations_manquantes)
    print("Questions générées:", questions)

    # Vérifications simples
    assert len(info.informations_manquantes) > 0, "Un ticket vague devrait avoir des infos manquantes"
    assert len(questions) <= 2, "Jamais plus de 2 questions"
    assert len(questions) > 0, "Au moins une question si des infos manquent"