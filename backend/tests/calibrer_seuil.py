"""Calibrage du seuil de pertinence du RAG (RAG-7).

Le seuil arbitre entre deux erreurs opposées :
- trop bas, les bonnes procédures sont écartées et le système répond « aucune
  source » à des questions qu'il pouvait traiter ;
- trop haut, des passages hors sujet remontent et le modèle génère une réponse
  fondée sur du bruit.

Ce script balaie les valeurs candidates sur le jeu de test et affiche, pour
chacune, le rappel sur les questions couvertes et le taux de rejet correct sur
les questions hors corpus. N'utilise que des embeddings locaux : aucun appel
LLM, donc aucun quota consommé.
"""

import json
from pathlib import Path

from src.rag import _interroger, charger_kb, ingerer, nombre_de_fragments

RACINE = Path(__file__).resolve().parent
SEUILS = [0.35, 0.45, 0.55, 0.58, 0.59, 0.60, 0.61, 0.62, 0.65, 0.70, 0.80]


def main() -> None:
    if nombre_de_fragments() == 0:
        ingerer(charger_kb())

    jeu = json.load(open(RACINE / "eval_rag.json", encoding="utf-8"))
    couvertes = [q for q in jeu if not q.get("hors_corpus")]
    hors_corpus = [q for q in jeu if q.get("hors_corpus")]

    # Une seule interrogation par question, réutilisée pour tous les seuils.
    total = nombre_de_fragments()
    resultats_couvertes = [
        (q, _interroger(q["question"], 4, {"categorie": q["categorie"]}, total))
        for q in couvertes
    ]
    resultats_hors = [
        (q, _interroger(q["question"], 4, {"categorie": q["categorie"]}, total))
        for q in hors_corpus
    ]

    print("\nDistance à la source attendue (questions couvertes) :")
    distances_bonnes = []
    for q, res in resultats_couvertes:
        correspondances = [r["distance"] for r in res if r["source_id"] == q["source_attendue"]]
        if correspondances:
            distances_bonnes.append(min(correspondances))
            print(f"  {q['id']}  {min(correspondances):.3f}  -> {q['source_attendue']}")
        else:
            print(f"  {q['id']}  ABSENTE du top-4 -> {q['source_attendue']}")

    print("\nDistance du meilleur passage (questions hors corpus) :")
    for q, res in resultats_hors:
        meilleure = min((r["distance"] for r in res), default=None)
        libelle = f"{meilleure:.3f}" if meilleure is not None else "aucun"
        print(f"  {q['id']}  {libelle}")

    print(f"\n{'Seuil':>7}{'Rappel@4':>11}{'Rejet hors-corpus':>20}{'Compromis':>12}")
    print("-" * 52)
    for seuil in SEUILS:
        trouvees = sum(
            any(r["source_id"] == q["source_attendue"] and r["distance"] <= seuil for r in res)
            for q, res in resultats_couvertes
        )
        rejetees = sum(
            not any(r["distance"] <= seuil for r in res) for _, res in resultats_hors
        )
        rappel = trouvees / len(couvertes)
        rejet = rejetees / len(hors_corpus)
        # Moyenne harmonique : un seuil n'est bon que s'il réussit les deux.
        compromis = (
            2 * rappel * rejet / (rappel + rejet) if (rappel + rejet) else 0.0
        )
        print(f"{seuil:>7.2f}{rappel:>10.0%}{rejet:>19.0%}{compromis:>12.2f}")


if __name__ == "__main__":
    main()
