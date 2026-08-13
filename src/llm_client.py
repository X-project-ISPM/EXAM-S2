"""Point d'appel unique vers le LLM (Google AI Studio / Gemini API).

Tout le pipeline passe par `llm_call` : classification, diagnostic, RAG et
garde-fous. Ce point de passage unique est ce qui permettra de brancher
l'observabilité des prompts (OBS-6, §5.4 du sujet) en un seul endroit plutôt
que sur chaque site d'appel.
"""

import logging
import re
import threading
import time
from functools import lru_cache

from google import genai
from google.genai import types
from pydantic import BaseModel

from config import config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Échec d'appel au LLM, déjà traduit en erreur métier.

    L'orchestrateur l'attrape pour dégrader proprement en `action: escalade`
    plutôt que de laisser remonter une 500 nue (§2, gestion d'erreurs).
    """


class QuotaDepasseError(LLMError):
    """Quota Gemini épuisé malgré les tentatives de réémission."""


def _delai_suggere(message: str) -> float | None:
    """Extrait le délai que l'API elle-même recommande d'attendre.

    Gemini renvoie « Please retry in 5.79s » dans le corps d'une 429 :
    respecter ce délai est plus efficace qu'un backoff exponentiel aveugle.
    """
    correspondance = re.search(r"retry in (\d+(?:\.\d+)?)s", message)
    return float(correspondance.group(1)) if correspondance else None


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    # Construction différée : genai.Client() exige une clé valide dès
    # l'instanciation, donc la construire au chargement du module
    # empêcherait d'importer src.llm_client tant que GEMINI_API_KEY n'est pas
    # configurée — y compris pour les tests qui n'appellent jamais le réseau.
    if not config.gemini_api_key:
        raise LLMError(
            "GEMINI_API_KEY absente. Copier .env.example vers .env et y coller "
            "la clé obtenue sur https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=config.gemini_api_key)


_dernier_appel: float = 0.0
_verrou_debit = threading.Lock()


def _attendre_son_tour() -> None:
    """Espace les appels pour rester sous la limite de requêtes par minute.

    Subir une 429 coûte le délai de reprise imposé par l'API (parfois plus
    d'une minute) ; attendre quelques secondes en amont est nettement moins
    cher. Sérialisé par un verrou car FastAPI sert les requêtes en parallèle.
    """
    if config.llm_requetes_par_minute <= 0:
        return

    intervalle = 60.0 / config.llm_requetes_par_minute
    global _dernier_appel
    with _verrou_debit:
        attente = intervalle - (time.monotonic() - _dernier_appel)
        if attente > 0:
            time.sleep(attente)
        _dernier_appel = time.monotonic()


def _appeler_avec_reprise(contenu: str, parametres: types.GenerateContentConfig):
    """Appelle l'API en absorbant les dépassements de quota par minute.

    Le Free Tier plafonne à 15 requêtes/minute (valeur constatée pour
    gemini-3.5-flash-lite). Or le pipeline émet plusieurs appels par ticket :
    sans reprise, une démo enchaînant quelques tickets déclenche une 429 en
    pleine présentation. On réémet en respectant le délai indiqué par l'API.
    """
    derniere_erreur: Exception | None = None

    for tentative in range(config.llm_max_tentatives):
        try:
            _attendre_son_tour()
            return _get_client().models.generate_content(
                model=config.gemini_model,
                contents=contenu,
                config=parametres,
            )
        except Exception as e:
            message = str(e)
            est_quota = "RESOURCE_EXHAUSTED" in message or "429" in message
            if not est_quota:
                raise LLMError(f"Appel LLM échoué ({type(e).__name__}) : {e}") from e

            derniere_erreur = e
            if tentative == config.llm_max_tentatives - 1:
                break

            attente = _delai_suggere(message) or config.llm_attente_quota
            attente += 0.5  # marge : la fenêtre de quota est glissante
            logger.warning(
                "Quota atteint (tentative %d/%d), reprise dans %.1fs",
                tentative + 1,
                config.llm_max_tentatives,
                attente,
            )
            time.sleep(attente)

    raise QuotaDepasseError(
        f"Quota Gemini dépassé après {config.llm_max_tentatives} tentatives. "
        f"Free Tier limité à ~15 requêtes/minute — espacer les appels ou "
        f"changer de modèle via GEMINI_MODEL. Détail : {derniere_erreur}"
    ) from derniere_erreur


def llm_call(
    prompt_systeme: str,
    prompt_utilisateur: str,
    response_schema: type[BaseModel] | None = None,
) -> BaseModel | str:
    """Appelle le LLM et retourne soit du texte, soit un objet Pydantic validé.

    Quand `response_schema` est fourni, on s'appuie sur le mode JSON natif de
    l'API Gemini (`response_mime_type` + `response_schema`) plutôt que sur du
    parsing manuel : le modèle est contraint côté serveur, et `.parsed` rend
    directement une instance Pydantic déjà validée.
    """
    parametres = types.GenerateContentConfig(
        system_instruction=prompt_systeme,
        temperature=config.llm_temperature,
        max_output_tokens=config.llm_max_output_tokens,
    )
    if response_schema is not None:
        parametres.response_mime_type = "application/json"
        parametres.response_schema = response_schema

    reponse = _appeler_avec_reprise(prompt_utilisateur, parametres)

    if response_schema is None:
        return reponse.text or ""

    resultat = reponse.parsed
    if resultat is None:
        raise LLMError(
            f"Le modèle n'a pas produit de JSON conforme à {response_schema.__name__}. "
            f"Réponse brute : {(reponse.text or '')[:200]}"
        )
    return resultat
