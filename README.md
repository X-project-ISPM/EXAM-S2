# mAIntenance & Assistance

Assistant intelligent de support informatique : prend en charge un ticket depuis sa
soumission jusqu'à sa résolution ou son escalade. Hackathon ISPM — AI Engineering & ML.

> **État actuel** : pipeline complet opérationnel — classification, diagnostic, RAG,
> agent avec outils, garde-fous, sortie structurée, observabilité et orchestrateur sont
> tous branchés et testés. Détail de l'avancement, des mesures et des décisions dans
> [le backlog](DOCS/backlog-mAIntenance-assistant.md). Index des documents de remise
> (README, rapport technique, lancement, checklist, notes de démo) :
> [livrables/](livrables/README.md).

## Démo en ligne

| Composant | Lien |
|---|---|
| Frontend (Streamlit) | <https://exam-s2-aaqefovmmtwswjqwxs6cxp.streamlit.app/> |
| Backend (API, Swagger) | <https://exam-s2.onrender.com/docs#/default/traiter_tickets_traiter_post> |

Tier gratuit Render : l'instance backend se met en veille après inactivité, la première
requête suivant une pause peut prendre 30 à 60 s (cold start), pas une panne.

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
Interface (Streamlit, frontend/app.py)
        │
        ▼
Orchestrateur (FastAPI, backend/src/api.py + orchestrator.py)
        │
        ├─► Garde-fous en entrée (injection, escalade immédiate)
        │
        ├─► Classification (catégorie → priorité → équipe, routage déterministe)
        │
        ├─► Diagnostic (informations extraites, manques calculés en code)
        │
        ├─► RAG (base de connaissances, recherche + génération citée)
        │
        ├─► Agent (function calling, 8 outils, boucle bornée, validation humaine)
        │
        └─► Sortie structurée (JSON validé par Pydantic — `TicketDecision`)
                │
                ▼
        Ticket : résolution / demande d'info / escalade
```

Deux préoccupations transverses interceptent chaque étape : **observabilité**
(`backend/src/observability.py` — entrées/sorties, appels d'outils, appels LLM bruts,
latence, coût estimé, tous en JSONL) et **garde-fous** (`backend/src/guardrails.py` —
détection d'injection à deux couches, validation humaine sur les actions sensibles,
masquage des données sensibles avant tout log).

Le détail complet — prompts, modèles de données, stratégie d'évaluation — est dans
[DOCS/architecture-mAIntenance-assistant.md](DOCS/architecture-mAIntenance-assistant.md),
et le rapport technique synthétique (approche, RAG, outils, évaluation, sécurité,
limites) dans [DOCS/rapport-technique.md](DOCS/rapport-technique.md).

## Structure du code

Le code Python vit sous `backend/` (package `src`, installé en editable) ; l'interface
Streamlit reste à la racine.

| Chemin | Rôle |
|---|---|
| [backend/src/config.py](backend/src/config.py) | Configuration centralisée (modèle, seuils, chemins) |
| [backend/src/schemas.py](backend/src/schemas.py) | Contrats Pydantic : `TicketDecision`, `Classification`, `ValidationInput`… |
| [backend/src/models.py](backend/src/models.py) | Données métier (utilisateurs, équipements, KB…) + chargement JSON |
| [backend/src/llm_client.py](backend/src/llm_client.py) | Point d'appel unique vers Gemini (reprise sur quota, timeout, hook OBS-6) |
| [backend/src/classifier.py](backend/src/classifier.py) | Classification catégorie / priorité + routage équipe déterministe |
| [backend/src/diagnostic.py](backend/src/diagnostic.py) | Extraction d'informations + questions ciblées (scénario 3) |
| [backend/src/rag.py](backend/src/rag.py) | Découpage, index Chroma, recherche et génération citée |
| [backend/src/agent.py](backend/src/agent.py) | Boucle agent (function calling), validation humaine des actions sensibles |
| [backend/src/tools.py](backend/src/tools.py) | Les 8 outils du sujet (consultation + action) et leur exécution encadrée |
| [backend/src/guardrails.py](backend/src/guardrails.py) | Garde-fous anti-injection (2 couches) et masquage des données sensibles |
| [backend/src/sortie.py](backend/src/sortie.py) | Retry sur sortie non conforme, réponse d'erreur toujours contrôlée |
| [backend/src/observability.py](backend/src/observability.py) | Traces, appels d'outils, appels LLM bruts, coût estimé (JSONL) |
| [backend/src/orchestrator.py](backend/src/orchestrator.py) | Enchaîne les étapes, applique les règles métier, gère les dégradations |
| [backend/src/api.py](backend/src/api.py) | Endpoints FastAPI (`/tickets/traiter`, `/tickets/valider`, `/observabilite/traces`, `/health`, `/health/diagnostic`) |
| [frontend/app.py](frontend/app.py) | Tableau de bord Streamlit (Chat/Résolution, Observabilité, Explorateur de Données) |
| [backend/tests/](backend/tests/) | Tests + jeux de données et scripts d'évaluation |
| `backend/data/` | Données métier (JSON), `tickets_historique.json` incrémenté à l'exécution |
| `backend/logs/` | Traces d'observabilité (JSONL, générées à l'exécution, non versionnées) |
| `backend/chroma_db/` | Index vectoriel persistant de la base de connaissances (ré-ingéré automatiquement au démarrage s'il est vide) |
| `backend/Procfile`, `backend/runtime.txt` | Déploiement Render (commande de lancement, version Python) |

## Choix techniques

| Choix | Justification |
|---|---|
| **Google AI Studio / Gemini**, `gemini-3.5-flash-lite` | Aucun entraînement requis. Flash-Lite pour son débit : le pipeline fait 5 à 8 appels LLM par ticket, le débit prime sur la profondeur de raisonnement. Quota réel à vérifier sur [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit) — il dépend du compte et de la région. |
| **Sortie structurée native** (`response_schema`) | Le modèle est contraint côté serveur et rend une instance Pydantic déjà validée, plutôt qu'un JSON à parser puis re-valider. |
| **FastAPI + Pydantic** | Le schéma imposé par le sujet est validé automatiquement, et `/docs` expose le contrat sans travail supplémentaire. |
| **Streamlit** | Chat, JSON structuré et tableau de bord d'observabilité dans une seule techno, sans build frontend. |
| **Un seul process, pas de framework agent** | Sur 8h, la complexité réseau et le débogage d'un framework lourd coûteraient plus qu'ils n'apportent. Le pipeline est entièrement synchrone (endpoints FastAPI en `def`, exécutés dans le threadpool) — `/health` reste réactif pendant qu'un ticket se traite. |
| **Le code contresigne la décision de l'agent** | Catégorie et équipe reviennent toujours au routage déterministe (`classifier.router_vers_equipe`), la priorité ne peut qu'être relevée par l'agent, les sources citées sont recoupées avec les fragments réellement fournis, et les questions posées à l'utilisateur reprennent celles calculées par `diagnostic.py` — jamais une invention du modèle. |

`trace_id` est délibérément **hors** de `TicketDecision` : c'est une métadonnée de
routage (pour `/tickets/valider` et l'observabilité), pas une donnée métier. Il vit
dans l'enveloppe `TicketReponse`, ce qui laisse `TicketDecision` strictement conforme
au schéma du §5.3 du sujet.

## Tests et évaluation

```bash
.venv/Scripts/python -m pytest                 # 246 tests hors réseau (par défaut)
.venv/Scripts/python -m pytest -m reseau        # 13 tests réseau (appels réels à Gemini)
.venv/Scripts/python -m backend.tests.eval      # évaluation classification + RAG → eval_results.json
.venv/Scripts/python -m ruff check .            # lint
```

Les tests réseau sont exclus par défaut pour ne pas épuiser le quota Free Tier à chaque
exécution ; à lancer une fois en début de journée pour valider la clé, puis avant la démo.

### Résultats de classification

Sur 20 tickets couvrant les 8 catégories, dont 4 pièges de frontière, un ticket
volontairement vague, un truffé de fautes et un hors périmètre informatique :

| Métrique | Résultat |
|---|---|
| Exactitude catégorie | **100 %** (20/20) |
| Rappel et précision par catégorie | 100 % sur les 8 catégories |
| Exactitude priorité | **95 %** (19/20) |

Le prompt initial plafonnait à 80 % sur la priorité : les exemples few-shot ancraient le
modèle sur `basse` pour tout ce qui touchait aux mots de passe, y compris quand
l'utilisateur était totalement bloqué. Expliciter « ne pas se connecter = bloqué =
haute » et distinguer l'incident de sécurité *en cours* du simple signalement a corrigé
trois cas sur quatre. Le seul échec restant (EV-12, une habilitation manquante sur une
application) oppose deux lectures défendables du barème — conservé comme tel plutôt que
réétiqueté.

### Résultats du RAG

Corpus de 24 articles et 34 questions, dont 8 volontairement hors du corpus :

| Métrique | Résultat |
|---|---|
| Rappel@k (bonne source retrouvée) | **96,2 %** (25/26) |
| Précision des citations | **100 %** — aucune source inventée |
| Détection « pas de source » | **100 %** (8/8 signalées incertaines, aucune source citée) |

L'unique échec de rappel (RQ-22, « un fichier client a été envoyé par erreur à une
adresse externe » → article sur les fuites de données) n'a aucun recouvrement lexical
avec sa source et **a échoué proprement** : le système a signalé son incertitude et n'a
cité aucune source, plutôt que de répondre à partir d'un article hors sujet.

Détail complet dans [backend/tests/eval_results.json](backend/tests/eval_results.json).

### Comment le seuil de pertinence a été fixé

`backend/tests/calibrer_seuil.py` balaie les valeurs candidates sans consommer de quota
LLM (embeddings locaux uniquement). Enseignements principaux :

- **ChromaDB indexe en L2 au carré par défaut, pas en cosinus.** La collection est donc
  créée explicitement en espace cosinus.
- **Un seuil serré casse le rappel** : 0.35 (valeur initialement envisagée) donnait 0 %
  de rappel, les bonnes sources se situant entre 0.36 et 0.60.
- **Aucun seuil ne sépare le hors-corpus** sur le corpus élargi (marge de séparation
  négative, −0.10). Le seuil (0.75) reste un simple filet ; c'est le drapeau
  `incertain` produit à la génération qui porte la décision — 100 % de détection, y
  compris sur des pièges conçus pour provoquer une recombinaison de sources.
- **`k` a été mesuré, pas supposé** : le rappel passe de 92 % (k=4/6) à 96 % (k=8) et
  stagne ensuite.

Deux garde-fous indépendants protègent contre la « procédure inexistante » (§6) :
le modèle déclare lui-même son incertitude, et un contrôle déterministe (dans
`orchestrator.py` et `rag.py`) retire toute source citée qui ne figurait pas dans les
passages fournis.

## Sécurité et garde-fous

Deux couches en entrée (`check_injection()`) : mots-clés (précision) puis vérification
LLM (rappel), avec masquage systématique des données sensibles avant tout log ou
réponse dégradée. `escalade_immediate()` court-circuite tout le pipeline dès qu'une
tentative de manipulation est détectée — aucune classification, aucun outil, aucune
procédure générée. Détail des 3 attaques reformulées testées et des décisions prises
dans le [backlog](DOCS/backlog-mAIntenance-assistant.md#%EF%B8%8F-sécurité-et-garde-fous)
et le [rapport technique](DOCS/rapport-technique.md).

## Limites connues

- **Le modèle n'est pas parfaitement déterministe**, même à `temperature=0` : 4 appels
  identiques sur un ticket frontière ont donné 2 `basse` et 2 `moyenne`. La catégorie
  est restée stable sur les 4.
- **Quota Free Tier à ~15 requêtes/minute** (constaté sur `gemini-3.5-flash-lite`). Les
  appels sont lissés en amont et une reprise absorbe les dépassements résiduels, mais le
  délai de reprise imposé par l'API peut atteindre ~1 minute par tentative : un ticket
  peut exceptionnellement prendre plusieurs minutes si le quota est déjà tendu (vécu
  pendant le développement). Le budget de temps global de l'orchestrateur (120 s) ne
  protège pas la classification elle-même, seule étape bloquante du pipeline.
- **`generer_avec_retry()` (régénération sur sortie non conforme)** : gérée automatiquement par `sortie.py` avec repli propre en escalade en cas d'erreur de schéma persistent.
- **Corpus et Datasets complets** : l'ensemble des 6 fichiers de données métier (`kb.json`, `utilisateurs.json`, `equipements.json`, `services.json`, `incidents_actifs.json`, `tickets_historique.json`) sont présents dans `backend/data/`, validés par tests unitaires au démarrage et incrémentés dynamiquement à chaque nouveau ticket traité.
- **Optimisation Mémoire & Render** : RAG migré sur `ONNXMiniLM_L6_V2` pour garantir une empreinte mémoire inférieure à 512 Mo et éviter les erreurs 502 OOM sur le tier gratuit de Render.
- **Interface Streamlit** : Dashboard SaaS complet avec métriques Donut, graphiques avec infobulles interactives, zéro emoji (icônes vectorielles SVG) et explorateur de données interactif.

