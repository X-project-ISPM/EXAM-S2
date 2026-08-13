# mAIntenance & Assistance

Assistant intelligent de support informatique : prend en charge un ticket depuis sa
soumission jusqu'à sa résolution ou son escalade. Hackathon ISPM — AI Engineering & ML.

> **État actuel** : fondations + **classification opérationnelle et évaluée**.
> Diagnostic, RAG et agent restent à brancher — `POST /tickets/traiter` renvoie
> encore une décision factice. Voir [le backlog](DOCS/backlog-mAIntenance-assistant.md).

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
| [src/llm_client.py](src/llm_client.py) | Point d'appel unique vers Gemini, avec reprise sur quota |
| [src/classifier.py](src/classifier.py) | Classification catégorie / priorité + routage équipe |
| [src/rag.py](src/rag.py) | Découpage, index Chroma, recherche et génération citée |
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

## Tests et évaluation

```bash
.venv/Scripts/python -m pytest            # tests hors-ligne (34)
.venv/Scripts/python -m pytest -m reseau  # appels réels à Gemini (consomme du quota)
.venv/Scripts/python -m tests.eval        # évaluation de la classification
.venv/Scripts/python -m ruff check .      # lint
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
trois cas sur quatre.

Le passage de 90 % à 95 % constaté ensuite ne porte que sur un ticket, précisément celui
dont l'instabilité est mesurée plus bas : **il est dans le bruit** et ne doit pas être
attribué aux correctifs. Seul l'écart 80 % → 90 %, qui porte sur trois tickets aux
causes identifiées, est significatif.

Le seul échec restant (EV-12, une habilitation manquante sur une application) oppose
deux lectures défendables du barème — il est conservé comme tel plutôt que réétiqueté.

### Résultats du RAG

Corpus de 24 articles (26 fragments) et 34 questions, dont 8 volontairement hors du
corpus. Les questions couvrent les paraphrases, les fautes d'orthographe, les requêtes
très courtes, les procédures voisines à départager et un article long découpé en
plusieurs fragments.

| Métrique | Résultat |
|---|---|
| Rappel@k (bonne source retrouvée) | **96 %** (25/26) |
| Précision des citations | **100 %** — aucune source inventée |
| Détection « pas de source » | **100 %** (8/8 signalées incertaines, aucune source citée) |

L'unique échec de rappel (RQ-22, « un fichier client a été envoyé par erreur à une
adresse externe » → article sur les fuites de données) n'a aucun recouvrement lexical
avec sa source : il demande une inférence que l'embedding seul ne fait pas. Point
important, **il a échoué proprement** — le système a signalé son incertitude et n'a cité
aucune source, plutôt que de répondre à partir d'un article hors sujet. Une recherche
hybride (lexicale + vectorielle) est la piste identifiée pour ce type de cas.

Les huit questions hors corpus incluent trois pièges conçus pour tenter la
recombinaison : une procédure de restauration inexistante alors que le corpus mentionne
les sauvegardes, un mot de passe d'imprimante lexicalement très proche de deux articles
réels, et une durée de conservation qu'on pourrait fabriquer en croisant deux articles
partiels. Toutes ont été refusées.

Détail complet dans `tests/eval_results.json` (généré).

### Comment le seuil de pertinence a été fixé

`tests/calibrer_seuil.py` balaie les valeurs candidates sans consommer de quota LLM
(embeddings locaux uniquement). Trois enseignements ont orienté la conception :

- **ChromaDB indexe en L2 au carré par défaut, pas en cosinus.** La collection est donc
  créée explicitement en espace cosinus ; sans cela le seuil s'appliquerait à une échelle
  double et filtrerait silencieusement de travers.
- **Un seuil serré casse le rappel.** Les bonnes sources se situent entre 0.36 et 0.60 :
  la valeur de 0.35 initialement envisagée donnait 0 % de rappel.
- **Aucun seuil ne sépare le hors-corpus.** Sur le corpus élargi, les plages se
  chevauchent franchement : la meilleure correspondance d'une question hors corpus
  descend à 0.49, sous plusieurs bonnes réponses. La marge de séparation est donc
  **négative** (−0.10). Le seuil est volontairement large (0.75, simple filet contre les
  rapprochements absurdes) et c'est le drapeau `incertain` produit à la génération qui
  porte la décision — mesuré à 100 % de détection, y compris sur les pièges conçus pour
  provoquer une recombinaison.
- **Le modèle multilingue n'apporte rien ici.** Comparé sur le pipeline réel, il obtient
  le même rappel (92 % avant l'ajustement de `k`) avec une marge de séparation nettement
  plus mauvaise (−0.38 contre −0.10) et deux fois plus de couches. Le modèle anglais
  `all-MiniLM-L6-v2` est conservé sur cette base, malgré un corpus francophone.
- **`k` a été mesuré, pas supposé** : le rappel passe de 92 % (k=4 ou 6) à 96 % (k=8) et
  stagne ensuite. La détection hors-corpus reste à 100 % malgré les passages
  supplémentaires.

Deux garde-fous indépendants protègent contre la « procédure inexistante » (§6) :
le modèle déclare lui-même son incertitude, et un contrôle déterministe retire toute
source citée qui ne figurait pas dans les passages fournis.

## Limites connues

- **Le modèle n'est pas parfaitement déterministe**, même à `temperature=0` : 4 appels
  identiques sur un ticket frontière ont donné 2 `basse` et 2 `moyenne`. La catégorie
  est restée stable sur les 4. Les chiffres de priorité portent donc une incertitude de
  l'ordre d'un ticket sur 20.
- **Quota Free Tier à 15 requêtes/minute** (constaté sur `gemini-3.5-flash-lite`). Les
  appels sont lissés en amont (`llm_requetes_par_minute`) et une reprise absorbe les
  dépassements résiduels, mais cela impose un plancher d'environ 4 s par appel LLM :
  une démo enchaînant les tickets rapidement restera perceptiblement lente.
- Le jeu d'évaluation est **rédigé à la main** : il reflète notre compréhension du
  barème, pas les données réelles du hackathon. Les priorités attendues comportent des
  cas légitimement discutables (EV-12 en est un).
- **Le corpus de `data/kb.json` est un corpus d'amorçage rédigé par nos soins**, destiné
  à être remplacé par celui fourni le jour du hackathon. Les 100 % du RAG sont donc
  obtenus sur un corpus et des questions écrits par la même équipe : ils valident la
  chaîne technique, pas la difficulté réelle. Le seuil est à recalibrer
  (`python -m tests.calibrer_seuil`) dès le corpus réel disponible.
- Diagnostic, RAG et agent ne sont pas branchés : la décision retournée par l'API reste
  un stub.
- Les données du hackathon ne sont pas encore dans `data/` ; le chargeur tolère leur
  absence pour ne pas bloquer le démarrage, mais les noms de fichiers attendus
  ([src/models.py](src/models.py)) devront être alignés sur ceux réellement fournis, de
  même que le vocabulaire d'équipes (`EQUIPES_PAR_CATEGORIE`).
