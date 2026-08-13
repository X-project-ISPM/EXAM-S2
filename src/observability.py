"""Observabilité — traces, appels d'outils et appels LLM (§5.4 du sujet).

Trois journaux JSONL indépendants, un événement par ligne :

- `traces.jsonl`     : une entrée par ticket traité (OBS-1) — décision finale,
  latence globale. Alimente `GET /observabilite/traces` (OBS-4).
- `tool_calls.jsonl` : une entrée par appel d'outil de l'agent (OBS-1),
  branché via `tools.set_log_appel(log_tool_call)` — même contrat de
  signature que défini là-bas, pour ne pas créer de dépendance circulaire
  entre `tools.py` et ce module.
- `llm_calls.jsonl`  : une entrée par appel au modèle génératif — prompts et
  réponses bruts, exigés explicitement au §5.4 ("prompts et réponses du
  modèle génératif"). Branché directement dans `llm_call()` et
  `llm_call_with_tools()` (OBS-6), le point de passage unique du pipeline.

Format JSON Lines : un fichier qui grossit en continu, consultable sans base
de données. Toute valeur passe par `guardrails.masquer_objet()` avant
écriture (SEC-5) — un ticket peut contenir un mot de passe en clair, il ne
doit pas se retrouver tel quel dans des logs relus pendant la démo.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import config
from src.guardrails import masquer_objet

# --- Écriture ------------------------------------------------------------


def _horodatage() -> str:
    return datetime.now(UTC).isoformat()


def _ecrire_jsonl(fichier: Path, evenement: dict[str, Any]) -> None:
    """Ajoute une ligne JSON à un fichier JSONL, en créant le dossier si besoin.

    N'échoue jamais bruyamment : un souci d'écriture de log ne doit pas faire
    échouer le traitement d'un ticket, l'observabilité est un effet de bord,
    pas une dépendance dure du pipeline (cohérent avec `tools.executer_outil`,
    qui ne laisse pas non plus une erreur d'outil remonter en exception nue).
    """
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with open(fichier, "a", encoding="utf-8") as f:
            f.write(json.dumps(masquer_objet(evenement), ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def _lire_dernieres_lignes(fichier: Path, limite: int) -> list[dict[str, Any]]:
    if not fichier.exists():
        return []
    with open(fichier, encoding="utf-8") as f:
        lignes = [json.loads(ligne) for ligne in f if ligne.strip()]
    return list(reversed(lignes[-limite:]))


# --- Traces (OBS-1, OBS-4) ------------------------------------------------


def log_trace(
    trace_id: str,
    ticket: Any,
    classification: Any | None,
    contexte: list[dict[str, Any]] | None,
    decision: Any,
    latence_ms: float,
) -> None:
    """Journalise le traitement complet d'un ticket : une ligne par appel à
    `POST /tickets/traiter`, décision finale incluse.

    Signature imposée par `orchestrator.set_log_trace()` (OBS-2) — pas celle,
    plus simple, d'origine (`description`/`decision: dict`/`erreur`) : cette
    dernière ne correspondait à aucun appelant réel une fois l'orchestrateur
    écrit, `ticket`/`classification`/`decision` y sont des objets Pydantic, pas
    des dicts déjà aplatis. `ticket`/`classification` restent `None`-safe
    (`getattr`) : l'orchestrateur appelle ce hook même quand les garde-fous ou
    la classification ont court-circuité le pipeline avant que ces objets
    n'existent.
    """
    _ecrire_jsonl(
        config.fichier_traces,
        {
            "horodatage": _horodatage(),
            "trace_id": trace_id,
            "description": getattr(ticket, "description", None),
            "categorie_classifiee": getattr(classification, "categorie", None),
            "priorite_classifiee": getattr(classification, "priorite", None),
            "confiance_classification": getattr(classification, "confiance", None),
            "nb_documents_contexte": len(contexte) if contexte else 0,
            "decision": decision.model_dump() if hasattr(decision, "model_dump") else decision,
            "latence_ms": round(latence_ms, 1),
        },
    )


def lire_dernieres_traces(limite: int = 50) -> list[dict[str, Any]]:
    """Relit les `limite` dernières traces, les plus récentes en premier.
    Consommé par `GET /observabilite/traces` (OBS-4)."""
    return _lire_dernieres_lignes(config.fichier_traces, limite)


# --- Appels d'outils (OBS-1) -----------------------------------------------
# Signature imposée par `tools.set_log_appel()` : ne pas la changer sans
# mettre à jour l'appel à `set_log_appel(log_tool_call)` (voir api.py).


def log_tool_call(
    trace_id: str,
    nom: str,
    params: dict[str, Any],
    resultat: Any,
    statut: str,
    latence_ms: float,
) -> None:
    _ecrire_jsonl(
        config.fichier_tool_calls,
        {
            "horodatage": _horodatage(),
            "trace_id": trace_id,
            "outil": nom,
            "params": params,
            "resultat": resultat,
            "statut": statut,
            "latence_ms": latence_ms,
        },
    )


def lire_derniers_appels_outils(limite: int = 50) -> list[dict[str, Any]]:
    return _lire_dernieres_lignes(config.fichier_tool_calls, limite)


# --- Coût estimé (OBS-3) ----------------------------------------------------
# Tarifs approximatifs (USD / million de tokens), volontairement grossiers :
# le Free Tier utilisé pour la démo est en réalité gratuit. Ce chiffre donne
# un ordre de grandeur exploitable si le projet basculait sur un tier payant
# — "éventuellement le coût estimé des appels" (§5.4), pas une facture exacte.

COUT_PAR_MILLION_TOKENS_ENTREE_USD = 0.10
COUT_PAR_MILLION_TOKENS_SORTIE_USD = 0.40


def estimer_cout(tokens_entree: int | None, tokens_sortie: int | None) -> float | None:
    if tokens_entree is None or tokens_sortie is None:
        return None
    return round(
        tokens_entree / 1_000_000 * COUT_PAR_MILLION_TOKENS_ENTREE_USD
        + tokens_sortie / 1_000_000 * COUT_PAR_MILLION_TOKENS_SORTIE_USD,
        6,
    )


# --- Appels LLM (OBS-6) ------------------------------------------------------


def log_llm_call(
    prompt_systeme: str,
    contenu: Any,
    reponse_texte: str,
    modele: str,
    latence_ms: float,
    tokens_entree: int | None = None,
    tokens_sortie: int | None = None,
    etape: str = "non_precisee",
    trace_id: str | None = None,
) -> None:
    """Journalise un appel brut au modèle génératif — prompt et réponse tels
    quels, exigé au §5.4 du sujet.

    `trace_id` est optionnel : sa propagation jusqu'ici (pour relier un appel
    LLM au ticket qui l'a déclenché) est le travail d'OBS-2/ORCH-1, pas encore
    fait. En attendant, `etape` (classification/diagnostic/rag/agent/...)
    identifie au moins la provenance de l'appel dans `llm_calls.jsonl`.
    """
    _ecrire_jsonl(
        config.fichier_llm_calls,
        {
            "horodatage": _horodatage(),
            "trace_id": trace_id,
            "etape": etape,
            "modele": modele,
            "prompt_systeme": prompt_systeme,
            "contenu": contenu,
            "reponse": reponse_texte,
            "tokens_entree": tokens_entree,
            "tokens_sortie": tokens_sortie,
            "cout_estime_usd": estimer_cout(tokens_entree, tokens_sortie),
            "latence_ms": round(latence_ms, 1),
        },
    )


def lire_derniers_appels_llm(limite: int = 50) -> list[dict[str, Any]]:
    return _lire_dernieres_lignes(config.fichier_llm_calls, limite)


class ChronoLatence:
    """Petit chronomètre pour mesurer une latence en millisecondes.

    `with ChronoLatence() as chrono: ...` puis `chrono.ms` — évite de
    dupliquer `time.time()` avant/après à chaque site d'appel de `llm_call`.
    """

    def __enter__(self) -> "ChronoLatence":
        self._debut = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.ms = (time.perf_counter() - self._debut) * 1000
