# mAIntenance & Assistance

Assistant intelligent de support informatique : prend en charge un ticket depuis sa
soumission jusqu'à sa résolution ou son escalade. Hackathon ISPM — AI Engineering & ML.

> **État actuel** : fondations posées (schémas, config, client LLM, API, frontend).
> Le pipeline métier (classification, diagnostic, RAG, agent) est en cours —
> `POST /tickets/traiter` renvoie encore une décision factice. Voir
> [le backlog](DOCS/backlog-mAIntenance-assistant.md).

## Démarrage rapide

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"    # Linux/macOS : .venv/bin/pip

cp .env.example .env                      # puis renseigner GEMINI_API_KEY
./run.sh                                  # Windows : .\run.ps1
```

- API : <http://localhost:8000> — documentation interactive sur `/docs`
- Interface : <http://localhost:8501>

La clé Gemini se génère sur <https://aistudio.google.com/apikey>. `.env` n'est jamais
versionné ; seul `.env.example` l'est, avec des valeurs vides.

## Architecture

```
Interface (Streamlit)
        │
        ▼
Orchestrateur (FastAPI)
        │
   ┌────┴────┐
   ▼         ▼
Base de    Agent + outils
connais-   (function calling,
sances     boucle bornée)
(RAG)         │
   └────┬────┘
        ▼
Sortie structurée (JSON validé par Pydantic)
        │
        ▼
Ticket : résolution / demande d'info / escalade
```

Deux préoccupations transverses interceptent chaque étape : **observabilité** (chaque
entrée/sortie, appel d'outil et latence est tracé) et **garde-fous** (détection
d'injection en entrée, validation humaine sur les actions sensibles).

Le détail complet — prompts, modèles de données, stratégie d'évaluation — est dans
[DOCS/architecture-mAIntenance-assistant.md](DOCS/architecture-mAIntenance-assistant.md).

## Structure du code

| Chemin | Rôle |
|---|---|
| [src/config.py](src/config.py) | Configuration centralisée (modèle, seuils, chemins) |
| [src/schemas.py](src/schemas.py) | Contrat de sortie : `TicketDecision`, `TicketReponse`… |
| [src/models.py](src/models.py) | Données métier (utilisateurs, équipements, KB) + chargement |
| [src/llm_client.py](src/llm_client.py) | Point d'appel unique vers Gemini |
| [src/api.py](src/api.py) | Endpoints FastAPI |
| [frontend/app.py](frontend/app.py) | Interface de démonstration Streamlit |
| [tests/](tests/) | Tests + jeux de données d'évaluation |
| `logs/` | Traces d'observabilité (JSONL, générées à l'exécution) |

## Choix techniques

| Choix | Justification |
|---|---|
| **Google AI Studio / Gemini**, `gemini-3.5-flash-lite` | Aucun entraînement requis. Flash-Lite pour son débit : le pipeline fait plusieurs appels LLM par ticket, le débit prime sur la profondeur de raisonnement. Quota réel à vérifier sur [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit) — il dépend du compte et de la région. |
| **Sortie structurée native** (`response_schema`) | Le modèle est contraint côté serveur et rend une instance Pydantic déjà validée, plutôt qu'un JSON à parser puis re-valider. |
| **FastAPI + Pydantic** | Le schéma imposé par le sujet est validé automatiquement, et `/docs` expose le contrat sans travail supplémentaire. |
| **Streamlit** | Chat, JSON structuré et tableau de bord d'observabilité dans une seule techno, sans build frontend. |
| **Un seul process, pas de framework agent** | Sur 8h, la complexité réseau et le débogage d'un framework lourd coûteraient plus qu'ils n'apportent. |

`trace_id` est délibérément **hors** de `TicketDecision` : c'est une métadonnée de
routage (pour `/tickets/valider` et l'observabilité), pas une donnée métier. Il vit
dans l'enveloppe `TicketReponse`, ce qui laisse `TicketDecision` strictement conforme
au schéma du §5.3 du sujet.

## Tests

```bash
.venv/Scripts/python -m pytest          # tests hors-ligne
.venv/Scripts/python -m pytest -m reseau  # appels réels à Gemini (consomme du quota)
.venv/Scripts/python -m ruff check .    # lint
```

Les tests réseau sont exclus par défaut pour ne pas épuiser le quota Free Tier à chaque
exécution ; à lancer une fois en début de journée pour valider la clé, puis avant la démo.

## Limites connues

- Le pipeline métier n'est pas encore branché : la décision retournée est un stub.
- Les données du hackathon ne sont pas encore dans `data/` ; le chargeur tolère leur
  absence pour ne pas bloquer le démarrage, mais les noms de fichiers attendus
  ([src/models.py](src/models.py)) devront être alignés sur ceux réellement fournis.
