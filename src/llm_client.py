import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


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
    structurée exigée au §5.3 du sujet)."""
    if response_schema is not None:
        prompt_systeme = (
            f"{prompt_systeme}\n\nRéponds STRICTEMENT en JSON conforme à ce schéma, "
            f"sans aucun texte hors du JSON :\n{json.dumps(response_schema.model_json_schema())}"
        )

    reponse = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=prompt_systeme,
        messages=[{"role": "user", "content": prompt_utilisateur}],
    )
    texte_brut = reponse.content[0].text

    if response_schema is not None:
        return response_schema.model_validate_json(_extraire_json(texte_brut))
    return texte_brut
