"""Point d'appel unique vers le LLM (Google AI Studio / Gemini API).

Tout le pipeline passe par `llm_call` : classification, diagnostic, RAG et
garde-fous. Ce point de passage unique est ce qui permettra de brancher
l'observabilité des prompts (OBS-6, §5.4 du sujet) en un seul endroit plutôt
que sur chaque site d'appel.
"""

from functools import lru_cache

from google import genai
from google.genai import types
from pydantic import BaseModel

from src.config import config


class LLMError(RuntimeError):
    """Échec d'appel au LLM, déjà traduit en erreur métier.

    L'orchestrateur l'attrape pour dégrader proprement en `action: escalade`
    plutôt que de laisser remonter une 500 nue (§2, gestion d'erreurs).
    """


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

    try:
        reponse = _get_client().models.generate_content(
            model=config.gemini_model,
            contents=prompt_utilisateur,
            config=parametres,
        )
    except LLMError:
        raise
    except Exception as e:  # erreurs réseau, quota, authentification
        raise LLMError(f"Appel LLM échoué ({type(e).__name__}) : {e}") from e

    if response_schema is None:
        return reponse.text or ""

    resultat = reponse.parsed
    if resultat is None:
        raise LLMError(
            f"Le modèle n'a pas produit de JSON conforme à {response_schema.__name__}. "
            f"Réponse brute : {(reponse.text or '')[:200]}"
        )
    return resultat
