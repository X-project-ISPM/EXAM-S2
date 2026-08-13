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
    # Timeout d'un appel HTTP au modèle (ORCH-3). Sans borne explicite, une API
    # qui ne répond pas fige la requête FastAPI et le frontend attend
    # indéfiniment : la réponse dégradée ne partirait jamais. Généreux par
    # rapport aux 1-5 s observées sur flash-lite, pour ne pas couper un appel
    # simplement lent.
    llm_timeout_s: float = 30.0
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
    # ATTENTION : ChromaDB utilise L2 au carré par défaut, pas le cosinus. La
    # collection est créée explicitement en espace cosinus (voir rag.py) —
    # sans cela, ce seuil s'appliquerait à une échelle deux fois plus grande.
    # Seuil volontairement large (RAG-7, voir tests/calibrer_seuil.py).
    # Le calibrage isole une frontière nette sur le jeu de test — bonnes
    # sources jusqu'à 0.59, hors-corpus à partir de 0.61 — mais cette marge de
    # 0.016 ne survit pas à un changement de formulation : une requête courte
    # (« j'ai oublié mon mot de passe ») place sa bonne source à 0.63, donc
    # au-delà. Un seuil serré rejetterait ces requêtes légitimes.
    # Mesure comparative à 0.75 : rappel, précision des citations ET détection
    # hors-corpus restent à 100 %, le modèle jugeant lui-même les passages
    # insuffisants. Le garde-fou robuste est donc le drapeau `incertain` de la
    # génération ; ce seuil ne sert plus que de filet contre les
    # rapprochements absurdes.
    rag_seuil_pertinence: float = 0.75
    # Mesuré sur le corpus élargi : le rappel passe de 92 % (k=4 et k=6) à
    # 96 % (k=8), et stagne au-delà. Le surcoût en contexte est acceptable
    # puisque le modèle écarte de façon fiable les passages hors sujet.
    rag_k: int = 8
    rag_taille_chunk: int = 220  # en mots
    rag_chevauchement: int = 40
    # Empêche un article long de monopoliser le top-k avec ses propres
    # fragments, au détriment d'une seconde procédure pertinente.
    rag_max_fragments_par_source: int = 2
    rag_modele_embedding: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_collection: str = "base-de-connaissances"

    # --- Agent ---
    agent_max_iterations: int = 5  # §5.2 du sujet : contrôle du nombre d'actions

    # --- Orchestrateur (ORCH-1 / ORCH-3) ---
    # Budget de temps total d'un ticket. Le lissage de débit espace déjà les
    # appels de ~4,3 s (14 req/min) et le pipeline en émet 5 à 8 : un ticket
    # normal tient en 30-60 s. Au-delà du budget, les étapes optionnelles
    # (diagnostic, RAG, agent) sont sautées et la décision est construite avec
    # ce qui a déjà été obtenu, plutôt que de laisser l'utilisateur attendre.
    orchestrateur_budget_s: float = 120.0
    # En dessous de ce seuil, la classification est trop incertaine pour agir
    # sans relecture humaine (§6 du sujet : validation avant action).
    orchestrateur_seuil_confiance: float = 0.5

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
