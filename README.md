# mAIntenance & Assistance

Assistant intelligent de support informatique : prend en charge un ticket depuis sa
soumission jusqu'à sa résolution ou son escalade. Hackathon ISPM — AI Engineering & ML.

> **État actuel** : fondations + **classification** (évaluée) + **agent avec les
> 8 outils** (validation humaine incluse) opérationnels. Le pipeline complet de
> l'API — diagnostic, RAG, orchestration — est en cours de branchement.
> Voir [le backlog](DOCS/backlog-mAIntenance-assistant.md).

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
| [src/tools.py](src/tools.py) | Spécification et implémentation des 8 outils + exécution validée |
| [src/agent.py](src/agent.py) | Boucle agent (function calling, limite d'itérations, validation humaine) |
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

Détail complet dans `tests/eval_results.json` (généré).

### Résultats de Agents + Outils

La boucle agent est testée avec un LLM simulé : ce qu'on vérifie hors-ligne, ce sont
les mécanismes que le **code contrôle** (le modèle, lui, ne peut pas être évalué sans
quota). 48 tests couvrent la spécification, l'implémentation des 8 outils et la
mécanique de la boucle :

| Mécanisme vérifié | Résultat |
|---|---|
| Spécification conforme au §3.4 | 8/8 outils aux noms exacts du sujet, 4 consultations + 4 actions |
| Sensibilité des actions (§6) | `mettre_a_jour_ticket` et `escalader_vers_technicien` bloqués côté code, **0 exécution non approuvée** (vérifié : le registre est intact après une tentative) |
| Validation des paramètres (§5.2) | appels incomplets ou outils inconnus refusés avant exécution |
| Erreurs d'appel (§5.2) | toute exception interne (ticket inexistant…) capturée et renvoyée au modèle — jamais d'exception vers l'utilisateur |
| Contrôle du nombre d'actions (§5.2) | boucle bornée à 5 itérations ; limite atteinte → escalade propre, pas d'erreur nue |
| Validation humaine (§5.2/§6) | action sensible mise en attente ; exécution possible **uniquement** après approbation (chemin `/tickets/valider`) |
| Sortie structurée (§5.3) | réponse finale contrainte au schéma `TicketDecision` côté serveur + revalidée Pydantic ; sortie non conforme → erreur typée, dégradée par l'orchestrateur |
| Couverture | 30 tests outils + 9 tests agent, 1 test réseau (`-m reseau`) pour l'appel réel |

Limite mesurée : la mécanique est validée hors-ligne, mais le choix effectif des outils
par le modèle ne peut se juger qu'en appel réel — c'est l'objet du test réseau, à
exécuter une fois la clé configurée, et de la démo.

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
- L'agent est **testé avec un LLM simulé** (mécanique de boucle, blocage des actions
  sensibles, limite d'itérations) ; le test réseau réel (`-m reseau`) reste à valider
  en début de journée.
- Diagnostic, RAG et orchestration de l'API ne sont pas encore branchés au pipeline.
- Les données du hackathon ne sont pas encore dans `data/` ; le chargeur tolère leur
  absence pour ne pas bloquer le démarrage, mais les noms de fichiers attendus
  ([src/models.py](src/models.py)) devront être alignés sur ceux réellement fournis, de
  même que le vocabulaire d'équipes (`EQUIPES_PAR_CATEGORIE`).
