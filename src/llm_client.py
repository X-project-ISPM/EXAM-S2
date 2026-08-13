import os
from functools import lru_cache

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    # Construction différée : genai.Client() exige une clé valide dès
    # l'instanciation (contrairement à d'autres SDK LLM), donc la construire
    # au chargement du module empêcherait d'importer src.llm_client tant que
    # GEMINI_API_KEY n'est pas configurée — y compris pour des usages qui
    # n'appellent jamais réellement le LLM (tests, exploration de l'API).
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


# gemini-3.5-flash-lite : le modèle Free Tier au quota le plus généreux de la
# gamme Gemini (documenté par Google comme dédié au "high-throughput
# execution"). Le pipeline appelle le LLM plusieurs fois par ticket
# (classification, diagnostic, RAG, garde-fous), donc le débit prime sur la
# profondeur de raisonnement pour la majorité de ces appels. Les quotas
# exacts (RPM/RPD/TPM) sont spécifiques au compte/région et ne sont plus
# publiés de façon statique par Google : vérifier le quota réel du projet
# sur https://aistudio.google.com/rate-limit avant la démo.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _extraire_json(texte: str) -> str:
    texte = texte.strip()
    if texte.startswith("```"):
        texte = texte.strip("`")
        if texte.lower().startswith("json"):
            texte = texte[4:]
    return texte.strip()


def llm_call(
    prompt_systeme: str,
    prompt_utilisateur: str,
    response_schema: type[BaseModel] | None = None,
) -> BaseModel | str:
    """Point d'appel LLM unique et réutilisable par tout le pipeline
    (classification, diagnostic, RAG, garde-fous). Si `response_schema` est
    fourni, la réponse est validée contre ce schéma Pydantic (sortie
    structurée exigée au §5.3 du sujet), via le mode JSON natif de l'API
    Gemini plutôt qu'un parsing manuel."""
    kwargs = {}
    if response_schema is not None:
        kwargs["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": response_schema.model_json_schema(),
        }

    interaction = _get_client().interactions.create(
        model=MODEL,
        system_instruction=prompt_systeme,
        input=prompt_utilisateur,
        **kwargs,
    )
    texte_brut = interaction.output_text

    if response_schema is not None:
        return response_schema.model_validate_json(_extraire_json(texte_brut))
    return texte_brut
