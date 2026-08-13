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
    # Free Tier : ~15 requêtes/minute constatées. Le pipeline émettant
    # plusieurs appels par ticket, la reprise sur quota n'est pas optionnelle.
    llm_max_tentatives: int = 4
    llm_attente_quota: float = 6.0  # secondes, si l'API n'indique pas de délai
    # Lissage proactif : espacer les appels coûte moins cher que d'encaisser
    # une 429, dont le délai de reprise imposé par l'API dépasse la minute.
    # 0 désactive le lissage.
    llm_requetes_par_minute: int = 14  # marge sous la limite Free Tier de 15

    # --- Sortie structurée (OUT-2) ---
    # Nombre de tentatives de génération conforme au schéma avant d'abandonner :
    # le 2e essai inclut le message d'erreur de validation du 1er (§7 de
    # l'architecture). Chaque essai consomme un appel LLM, d'où 2 max.
    llm_max_essais_validation: int = 2

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
