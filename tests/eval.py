"""Évaluation de la classification (§4 du sujet : « résultats mesurables »).

Recall **et** précision par catégorie plutôt qu'une accuracy globale : avec des
catégories déséquilibrées (§7), une accuracy globale masque l'échec sur les
catégories rares, et le recall seul masque la sur-classification vers une
catégorie dominante.
"""

import json
from collections import defaultdict
from datetime import UTC
from pathlib import Path

from src.classifier import classify_ticket

RACINE = Path(__file__).resolve().parent
JEU_PAR_DEFAUT = RACINE / "eval_dataset.json"


def charger_jeu(chemin: Path = JEU_PAR_DEFAUT) -> list[dict]:
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def _metriques_par_categorie(paires: list[tuple[str, str]]) -> dict[str, dict]:
    """paires = [(predite, attendue), ...] -> métriques par catégorie."""
    stats = defaultdict(lambda: {"vp": 0, "fp": 0, "fn": 0})
    for predite, attendue in paires:
        if predite == attendue:
            stats[predite]["vp"] += 1
        else:
            stats[predite]["fp"] += 1
            stats[attendue]["fn"] += 1

    resultats = {}
    for categorie, s in sorted(stats.items()):
        vp, fp, fn = s["vp"], s["fp"], s["fn"]
        rappel = vp / (vp + fn) if (vp + fn) else None
        precision = vp / (vp + fp) if (vp + fp) else None
        resultats[categorie] = {
            "rappel": rappel,
            "precision": precision,
            "support": vp + fn,
            "predits": vp + fp,
        }
    return resultats


def evaluer_classification(chemin: Path = JEU_PAR_DEFAUT) -> dict:
    jeu = charger_jeu(chemin)
    details, paires_cat, paires_prio = [], [], []

    for exemple in jeu:
        resultat = classify_ticket(exemple["description"])
        categorie_ok = resultat.categorie == exemple["categorie_attendue"]
        priorite_ok = resultat.priorite == exemple["priorite_attendue"]

        paires_cat.append((resultat.categorie, exemple["categorie_attendue"]))
        paires_prio.append((resultat.priorite, exemple["priorite_attendue"]))
        details.append(
            {
                "id": exemple["id"],
                "description": exemple["description"],
                "difficulte": exemple.get("difficulte", "non_precisee"),
                "categorie_attendue": exemple["categorie_attendue"],
                "categorie_obtenue": resultat.categorie,
                "categorie_ok": categorie_ok,
                "priorite_attendue": exemple["priorite_attendue"],
                "priorite_obtenue": resultat.priorite,
                "priorite_ok": priorite_ok,
                "equipe": resultat.equipe,
                "confiance": round(resultat.confiance, 2),
            }
        )

    total = len(details)
    justes_cat = sum(d["categorie_ok"] for d in details)
    justes_prio = sum(d["priorite_ok"] for d in details)

    par_difficulte = defaultdict(lambda: {"total": 0, "justes": 0})
    for d in details:
        par_difficulte[d["difficulte"]]["total"] += 1
        par_difficulte[d["difficulte"]]["justes"] += d["categorie_ok"]

    return {
        "total": total,
        "exactitude_categorie": round(justes_cat / total, 3),
        "exactitude_priorite": round(justes_prio / total, 3),
        "par_categorie": _metriques_par_categorie(paires_cat),
        "par_priorite": _metriques_par_categorie(paires_prio),
        "par_difficulte": {
            k: {**v, "taux": round(v["justes"] / v["total"], 3)}
            for k, v in sorted(par_difficulte.items())
        },
        "echecs": [d for d in details if not d["categorie_ok"] or not d["priorite_ok"]],
        "details": details,
    }


def evaluer_rag(chemin: Path = RACINE / "eval_rag.json") -> dict:
    """Mesure les trois exigences du §5.1 : retrouver le bon document, citer
    des sources réellement utilisées, et signaler l'absence de source."""
    from src.rag import (
        charger_kb,
        generer_reponse_rag,
        ingerer,
        nombre_de_fragments,
        retrieve_context,
    )

    if nombre_de_fragments() == 0:
        ingerer(charger_kb())

    with open(chemin, encoding="utf-8") as f:
        jeu = json.load(f)

    details = []
    for question in jeu:
        fragments = retrieve_context(question["question"], categorie=question.get("categorie"))
        sources_retrouvees = [f["source_id"] for f in fragments]
        reponse = generer_reponse_rag(question["question"], fragments)

        hors_corpus = bool(question.get("hors_corpus"))
        attendue = question.get("source_attendue")

        details.append(
            {
                "id": question["id"],
                "question": question["question"],
                "hors_corpus": hors_corpus,
                "source_attendue": attendue,
                "sources_retrouvees": sources_retrouvees,
                "sources_citees": reponse.sources,
                "incertain": reponse.incertain,
                # Le bon document figure-t-il parmi les passages retenus ?
                "rappel_ok": (attendue in sources_retrouvees) if attendue else None,
                # Toute source citée provient-elle bien des passages fournis ?
                "citations_fondees": set(reponse.sources) <= set(sources_retrouvees),
                # Hors corpus : le système doit refuser d'affirmer.
                "rejet_ok": (reponse.incertain or not sources_retrouvees) if hors_corpus else None,
            }
        )

    couvertes = [d for d in details if not d["hors_corpus"]]
    hors = [d for d in details if d["hors_corpus"]]
    avec_citations = [d for d in couvertes if d["sources_citees"]]

    return {
        "total": len(details),
        "questions_couvertes": len(couvertes),
        "questions_hors_corpus": len(hors),
        "rappel_at_k": round(sum(d["rappel_ok"] for d in couvertes) / len(couvertes), 3),
        "precision_citations": (
            round(sum(d["citations_fondees"] for d in avec_citations) / len(avec_citations), 3)
            if avec_citations
            else None
        ),
        "detection_hors_corpus": round(sum(d["rejet_ok"] for d in hors) / len(hors), 3),
        "reponses_certaines_couvertes": round(
            sum(not d["incertain"] for d in couvertes) / len(couvertes), 3
        ),
        "echecs": [
            d
            for d in details
            if (d["rappel_ok"] is False) or (d["rejet_ok"] is False) or not d["citations_fondees"]
        ],
        "details": details,
    }


def afficher_rag(rapport: dict) -> None:
    print(f"\n{'=' * 62}")
    print(f"RAG — {rapport['total']} questions "
          f"({rapport['questions_couvertes']} couvertes, "
          f"{rapport['questions_hors_corpus']} hors corpus)")
    print(f"{'=' * 62}")
    print(f"Rappel@k (bonne source retrouvée)   : {rapport['rappel_at_k']:.0%}")
    precision = rapport["precision_citations"]
    print(f"Précision des citations             : "
          f"{precision:.0%}" if precision is not None else "n/a")
    print(f"Détection « pas de source »         : {rapport['detection_hors_corpus']:.0%}")
    print(f"Réponses assumées (couvertes)       : {rapport['reponses_certaines_couvertes']:.0%}")

    if rapport["echecs"]:
        print(f"\nÉCHECS ({len(rapport['echecs'])})")
        print("-" * 62)
        for e in rapport["echecs"]:
            print(f"\n[{e['id']}] {e['question'][:66]}")
            print(f"  attendu {e['source_attendue']} / retrouvé {e['sources_retrouvees']}")
            print(f"  citées {e['sources_citees']} | incertain={e['incertain']}")
    else:
        print("\nAucun échec.")


def afficher(rapport: dict) -> None:
    print(f"\n{'=' * 62}")
    print(f"CLASSIFICATION — {rapport['total']} tickets")
    print(f"{'=' * 62}")
    print(f"Exactitude catégorie : {rapport['exactitude_categorie']:.1%}")
    print(f"Exactitude priorité  : {rapport['exactitude_priorite']:.1%}")

    print(f"\n{'Catégorie':<26}{'Rappel':>9}{'Précis.':>9}{'Support':>9}")
    print("-" * 62)
    for categorie, m in rapport["par_categorie"].items():
        rappel = f"{m['rappel']:.0%}" if m["rappel"] is not None else "n/a"
        precision = f"{m['precision']:.0%}" if m["precision"] is not None else "n/a"
        print(f"{categorie:<26}{rappel:>9}{precision:>9}{m['support']:>9}")

    print(f"\n{'Difficulté':<26}{'Taux':>9}{'Total':>9}")
    print("-" * 62)
    for niveau, m in rapport["par_difficulte"].items():
        print(f"{niveau:<26}{m['taux']:>9.0%}{m['total']:>9}")

    if rapport["echecs"]:
        print(f"\nÉCHECS ({len(rapport['echecs'])})")
        print("-" * 62)
        for e in rapport["echecs"]:
            print(f"\n[{e['id']}] {e['description'][:70]}")
            if not e["categorie_ok"]:
                print(
                    f"  catégorie : attendu {e['categorie_attendue']}"
                    f" / obtenu {e['categorie_obtenue']}"
                )
            if not e["priorite_ok"]:
                print(
                    f"  priorité  : attendu {e['priorite_attendue']}"
                    f" / obtenu {e['priorite_obtenue']}"
                )
            print(f"  confiance : {e['confiance']}")
    else:
        print("\nAucun échec.")


def sauvegarder(rapport: dict, chemin: Path = RACINE / "eval_results.json") -> Path:
    """Persiste le rapport : c'est le livrable n°6 du sujet
    (« les résultats de l'évaluation »)."""
    from datetime import datetime

    from src.config import config

    charge_utile = {
        "date": datetime.now(UTC).isoformat(),
        "modele": config.gemini_model,
        "modele_embedding": config.rag_modele_embedding,
        "seuil_rag": config.rag_seuil_pertinence,
        **rapport,
    }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(charge_utile, f, ensure_ascii=False, indent=2)
    return chemin


if __name__ == "__main__":
    classification = evaluer_classification()
    afficher(classification)

    rag = evaluer_rag()
    afficher_rag(rag)

    chemin = sauvegarder({"classification": classification, "rag": rag})
    print(f"\nRapport écrit dans {chemin}")
