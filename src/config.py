"""Configuration centralisée du projet.

Un seul endroit pour les réglages qui changent entre le développement, les
tests et la démo (modèle LLM, seuils, chemins). Évite les `os.environ.get`
dispersés dans chaque module et rend les paramètres d'évaluation (seuil RAG,
limite d'itérations de l'agent) visibles et justifiables devant le jury.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RACINE = Path(__file__).resolve().parent.parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM (Google AI Studio) ---
    gemini_api_key: str = ""
    # Flash-Lite : modèle Free Tier au débit le plus élevé de la gamme Gemini.
    # Le pipeline fait plusieurs appels LLM par ticket, donc le débit prime
    # sur la profondeur de raisonnement pour la majorité de ces appels.
    gemini_model: str = "gemini-3.5-flash-lite"
    llm_max_output_tokens: int = 2048
    llm_temperature: float = 0.0  # déterminisme : classification reproductible

    # --- RAG ---
    rag_seuil_pertinence: float = 0.35  # distance cosinus, à calibrer (RAG-7)
    rag_k: int = 4
    rag_taille_chunk: int = 400
    rag_chevauchement: int = 50

    # --- Agent ---
    agent_max_iterations: int = 5  # §5.2 du sujet : contrôle du nombre d'actions

    # --- Chemins ---
    dossier_data: Path = RACINE / "data"
    dossier_logs: Path = RACINE / "logs"
    dossier_chroma: Path = RACINE / "chroma_db"

    @property
    def fichier_traces(self) -> Path:
        return self.dossier_logs / "traces.jsonl"

    @property
    def fichier_tool_calls(self) -> Path:
        return self.dossier_logs / "tool_calls.jsonl"

    @property
    def fichier_llm_calls(self) -> Path:
        return self.dossier_logs / "llm_calls.jsonl"


config = Config()
