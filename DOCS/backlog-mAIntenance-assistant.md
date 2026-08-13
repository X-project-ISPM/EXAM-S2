# Backlog de tickets — mAIntenance & Assistance

Organisé par bloc fonctionnel. Chaque ticket a un ID, une estimation indicative, et ses dépendances pour faciliter la répartition en équipe.

> **Aligné sur la révision de `architecture-mAIntenance-assistant.md`.** Cinq
> changements se répercutent ici : champ `resume` dans `TicketDecision`,
> `log_llm_call()` pour tracer les prompts/réponses bruts, double vérification
> LLM anti-injection passée d'optionnelle à obligatoire, `evaluer_classification()`
> qui calcule aussi la précision (pas seulement le recall), et le pattern
> `"system:"` corrigé pour éviter les faux positifs. Impact marqué **[MAJ]** sur
> chaque ticket concerné.

## 🔧 Setup & fondations (bloquant pour tout le reste)

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| SETUP-1 | Créer la structure de dossiers du projet + `requirements.txt` | 15 min | — |
| SETUP-2 **[MAJ]** | Définir `schemas.py` : `TicketInput`, `TicketDecision` (incl. `resume`), `Classification`, `DiagnosticInfo` (contrat figé) | 30 min | — |
| SETUP-3 | Charger les données fournies (tickets, KB, users, équipements, incidents, services) en objets Pydantic dans `models.py` | 45 min | SETUP-1 |
| SETUP-4 | Configurer l'accès à l'API LLM (clé, wrapper `llm_call()` réutilisable) | 20 min | — |
| SETUP-5 | Créer l'endpoint `POST /tickets/traiter` avec réponse **factice codée en dur** pour débloquer le frontend immédiatement | 20 min | SETUP-2 |

## 🏷️ Classification

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| ~~CLASS-1~~ ✅ | Prompt système few-shot, 8 catégories + pièges de frontière | 30 min | SETUP-4 |
| ~~CLASS-2~~ ✅ | `classify_ticket()` validé par `Classification` + routage déterministe vers l'équipe | 30 min | CLASS-1, SETUP-2 |
| ~~CLASS-3~~ ✅ | Règles de priorité (critique/haute/moyenne/basse), affinées après mesure | 20 min | CLASS-1 |
| ~~CLASS-4~~ ✅ | Filet de sécurité regex sur la cybersécurité (rattrapage, pas court-circuit) | 30 min | CLASS-2 |
| ~~CLASS-5~~ ✅ | 20 tickets évalués, prompt ajusté : priorité 80 % → 90 % | 30 min | CLASS-2 |

**Résultats mesurés** (`python -m tests.eval`, 20 tickets, `gemini-3.5-flash-lite`) :
catégorie **100 %** (rappel et précision à 100 % sur les 8 catégories, y compris les 4
pièges de frontière, le ticket vague et celui truffé de fautes) ; priorité **95 %**.

**Revue de code — 3 défauts trouvés et corrigés :**
1. *Faux positif regex* : « anti-virus » (avec trait d'union) déclenchait le filet
   sécurité, le tiret créant une frontière de mot avant « virus ». Une mise à jour
   d'antivirus partait en incident critique vers l'équipe sécurité.
2. *Confiance erronée* : lors d'un reclassement, la confiance du modèle — qui portait sur
   la catégorie qu'il avait choisie — était reportée telle quelle sur la catégorie
   substituée. Risque en aval : supprimer la validation humaine au moment précis où l'on
   contredit le modèle. La confiance est désormais plafonnée en cas de requalification.
3. *Verdict sollicité puis ignoré* : le prompt demandait au modèle de vérifier s'il
   s'agissait vraiment d'un incident de sécurité, mais la règle écrasait sa réponse quoi
   qu'il dise. Il adjudique maintenant explicitement (`incident_securite_avere`) et le
   filet ne reprend la main que si sa confiance est faible.

**Optimisation** : lissage proactif des appels sous la limite de 15 req/min. L'évaluation
complète s'exécute désormais sans aucune 429 — auparavant, chaque dépassement imposait
un délai de reprise pouvant atteindre 57 s.

Décisions prises pendant l'implémentation :
- **L'équipe n'est pas produite par le LLM** mais dérivée de la catégorie par table de
  correspondance. Lors d'un test, le modèle avait inventé `"Infrastructure et Reseau"`
  en texte libre — non reproductible et inexploitable pour du routage.
- **Le filet regex ne court-circuite pas le LLM**, il rattrape : forcer la catégorie sur
  un simple mot-clé casserait « courriel demandant mon mot de passe » (phishing, pas
  gestion de comptes).
- **Reprise sur quota ajoutée** dans `llm_client.py` : le Free Tier est plafonné à
  **15 requêtes/minute** (constaté), or le pipeline émettra ~4 appels par ticket.
- **Limite connue** : à `temperature=0`, 4 appels identiques sur un ticket frontière ont
  donné 2 `basse` / 2 `moyenne`. La catégorie est restée stable.

## 🔍 Diagnostic

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| DIAG-1 | Écrire le prompt d'extraction d'informations (`DiagnosticInfo`) | 25 min | SETUP-4 |
| DIAG-2 | Implémenter `extraire_diagnostic()` | 20 min | DIAG-1 |
| DIAG-3 | Implémenter `generer_questions()` à partir de `informations_manquantes` | 20 min | DIAG-2 |
| DIAG-4 | Tester le scénario 3 (demande incomplète) de bout en bout | 20 min | DIAG-3 |

## 📚 RAG

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| RAG-1 | Installer et configurer ChromaDB + fonction d'embeddings | 20 min | SETUP-1 |
| RAG-2 | Écrire la fonction de chunking du corpus | 30 min | — |
| RAG-3 | Ingérer le corpus fourni dans l'index vectoriel | 30 min | RAG-1, RAG-2 |
| RAG-4 | Implémenter `retrieve_context()` avec filtrage par catégorie et seuil de pertinence | 30 min | RAG-3 |
| RAG-5 | Écrire le prompt de génération avec citations obligatoires | 25 min | SETUP-4 |
| RAG-6 | Implémenter la détection "pas de source suffisante" (flag `incertain`) | 20 min | RAG-4, RAG-5 |
| RAG-7 | Calibrer le seuil de pertinence sur des exemples manuels | 20 min | RAG-4 |
| RAG-8 | Construire le jeu de test RAG (`eval_rag.json`) avec sources attendues | 30 min | RAG-3 |
| RAG-9 | Implémenter `evaluer_rag()` (recall@k, précision citations) | 25 min | RAG-8 |

## 🤖 Agent + outils

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| AGT-1 | Spécifier les 8 outils (nom, description, paramètres, sensibilité) dans `OUTILS` | 30 min | SETUP-3 |
| AGT-2 | Implémenter les 4 outils de consultation (`rechercher_utilisateur`, `consulter_equipement`, `verifier_etat_service`, `rechercher_incidents_actifs`) | 45 min | AGT-1, SETUP-3 |
| AGT-3 | Implémenter les 4 outils d'action (`creer_ticket`, `mettre_a_jour_ticket`, `affecter_ticket`, `escalader_vers_technicien`) | 45 min | AGT-1, SETUP-3 |
| AGT-4 | Implémenter `valider_parametres()` et `executer_outil()` avec gestion d'erreurs | 30 min | AGT-2, AGT-3 |
| AGT-5 | Implémenter la boucle `run_agent()` avec function calling et limite d'itérations | 45 min | AGT-4, SETUP-4 |
| AGT-6 | Brancher la logique de validation humaine (`attente_validation_humaine`) dans la boucle | 25 min | AGT-5 |
| AGT-7 | Tester le scénario 1 (incident courant) et 2 (incident urgent) de bout en bout | 30 min | AGT-5, RAG-4 |

## 📋 Sortie structurée

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| OUT-1 | Finaliser le schéma `TicketDecision` complet (le champ `resume` est déjà posé dans SETUP-2, ici on verrouille validateurs/types) | 15 min | SETUP-2 |
| OUT-2 | Implémenter la stratégie de retry sur échec de validation Pydantic | 25 min | OUT-1 |
| OUT-3 | Implémenter `reponse_erreur_controlee()` pour ne jamais renvoyer d'erreur nue | 20 min | OUT-1 |

## 🛡️ Sécurité et garde-fous

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| SEC-1 **[MAJ]** | Écrire `MOTS_CLES_INJECTION` en regex + `PATTERN_ROLE_SYSTEME` (le littéral `"system:"` seul donnait des faux positifs — ne détecter qu'en début de ligne) et `check_injection()` | 25 min | — |
| SEC-2 | Définir `OUTILS_SENSIBLES` et `est_sensible()` | 15 min | AGT-1 |
| SEC-3 | Implémenter `escalade_immediate()` pour les tickets malveillants détectés (construit un `TicketDecision` avec `resume`) | 20 min | SEC-1, OUT-1 |
| SEC-4 **[MAJ — n'est plus optionnel]** | Implémenter `verifier_intention_malveillante_llm()` et la fusionner dans `check_injection()` : c'est cette couche qui attrape les reformulations que les mots-clés ratent ("ignore ce qui précède"). Directement liée à l'axe sécurité noté (10 %) et au scénario 4 obligatoire — traiter en priorité, pas en fin de journée. | 30 min | SEC-1, SETUP-4 |
| SEC-5 | Masquer les données sensibles (mots de passe, identifiants) avant écriture dans les logs — couvre désormais aussi `logs/llm_calls.jsonl` | 15 min | OBS-1, OBS-6 |
| SEC-6 **[MAJ]** | Tester le scénario 4 (demande sensible/malveillante) **avec une formulation qui contourne les mots-clés**, pour vérifier que la couche LLM (SEC-4) rattrape ce que SEC-1 rate | 25 min | SEC-3, SEC-4, AGT-6 |

## 📊 Observabilité

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| OBS-1 | Implémenter `log_trace()` et `log_tool_call()` (écriture JSONL) | 30 min | OUT-1 |
| OBS-2 | Brancher les logs à chaque étape de l'orchestrateur | 20 min | OBS-1, ORCH-1 |
| OBS-3 | Implémenter l'estimation de coût (`estimer_cout()`) | 20 min | OBS-1 |
| OBS-4 | Implémenter l'endpoint `GET /observabilite/traces` | 15 min | OBS-1 |
| OBS-5 | Décomposer la latence par étape (classification/RAG/agent) dans chaque trace | 20 min | OBS-2 |
| OBS-6 **[NOUVEAU]** | Implémenter `log_llm_call()` (écrit dans `logs/llm_calls.jsonl`) et le brancher dans `llm_call()`/`llm_call_with_tools()` — un seul point d'instrumentation pour couvrir les 4 appels LLM du pipeline (classification, diagnostic, RAG, agent). Exigé explicitement au §5.4 du sujet ("prompts et réponses du modèle génératif"), pas couvert par OBS-1 qui ne logue que la décision finale. | 25 min | OBS-1, SETUP-4 |

## 🔗 Orchestrateur (intégration backend)

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| ORCH-1 **[MAJ]** | Écrire l'endpoint `POST /tickets/traiter` réel (remplace le stub de SETUP-5) | 45 min | CLASS-2, DIAG-2, RAG-4, AGT-5, SEC-1, SEC-4, OUT-1 |
| ORCH-2 | Implémenter `POST /tickets/valider` pour la confirmation humaine | 25 min | AGT-6 |
| ORCH-3 | Gérer les timeouts et erreurs API LLM avec réponse dégradée | 25 min | ORCH-1 |
| ORCH-4 | Endpoint `GET /health` | 10 min | — |
| ORCH-5 | Tests d'intégration bout-en-bout sur les 4 scénarios obligatoires | 40 min | ORCH-1, ORCH-2 |

## 🖥️ Frontend

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| FE-1 | Structure de base Streamlit (layout, sidebar, navigation) | 20 min | — |
| FE-2 | Zone de saisie + bouton envoi + appel à `POST /tickets/traiter` | 25 min | SETUP-5 (stub suffisant pour démarrer) |
| FE-3 **[MAJ]** | Affichage de la décision (résumé (`resume`) mis en avant en tête de réponse + métriques + `st.json`) | 25 min | FE-2 |
| FE-4 | Boutons de scénarios pré-remplis dans la sidebar | 20 min | FE-1 |
| FE-5 | UI de validation humaine (boutons approuver/rejeter) | 25 min | FE-3, ORCH-2 |
| FE-6 | Onglet Observabilité (liste des traces, métriques agrégées) | 30 min | OBS-4 |
| FE-7 | Gestion des erreurs réseau côté frontend | 15 min | FE-2 |
| FE-8 | Passage du stub à la vraie API une fois `ORCH-1` prêt | 15 min | ORCH-1, FE-2 |

## ✅ Évaluation

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| EVAL-1 | Construire `eval_dataset.json` (15-20 tickets, 8 catégories + cas difficiles) | 40 min | — |
| EVAL-2 **[MAJ]** | Implémenter `evaluer_classification()` — recall **et précision** par catégorie (matrice de confusion simple), pas l'accuracy seule : une sur-classification vers la catégorie dominante doit rester visible | 30 min | EVAL-1, CLASS-2 |
| EVAL-3 | Implémenter `evaluer_scenarios_obligatoires()` | 20 min | ORCH-5 |
| EVAL-4 | Exécuter toutes les évaluations et consigner les résultats (`tests/run_eval.py` → `tests/eval_results.json`, le livrable "résultats de l'évaluation") | 20 min | EVAL-2, EVAL-3, RAG-9 |
| EVAL-5 | Analyse des erreurs et limites (rédaction courte) | 25 min | EVAL-4 |

## 📄 Livrables et documentation

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| DOC-1 | Rédiger `README.md` (architecture, choix, limites, lancement) | 45 min | Tout le reste (en fin de journée) |
| DOC-2 | Rédiger le rapport technique synthétique | 45 min | EVAL-4 |
| DOC-3 | Écrire `run.sh` (fichier de lancement) | 15 min | ORCH-4, FE-1 |
| DOC-4 | Vérifier la checklist de remise complète (8 livrables, 4 scénarios, 3 points de contrôle) | 20 min | Tout |
| DOC-5 | Préparer/répéter la démo (ordre des scénarios, discours) | 30 min | ORCH-5, FE-8 |

---

## Ordre de priorité si le temps manque

Si tout ne peut pas être fini, sacrifier dans cet ordre (du moins critique au plus critique) :
1. CLASS-4 (règles hybrides) — optionnel dès le départ
2. OBS-5 (décomposition de la latence par étape) — confort pour la démo, pas un point de contrôle noté
3. OBS-3 (estimation de coût) — nice-to-have, pas dans les 4 scénarios obligatoires
4. RAG-7 (calibration fine du seuil) — une valeur par défaut raisonnable suffit

**Ne jamais sacrifier** : ORCH-5 (tests des 4 scénarios), **SEC-3/SEC-4/SEC-6** (chaîne
complète du scénario sensible — la couche mots-clés seule échoue dès que l'attaque est
reformulée, SEC-4 n'est plus dans la liste des optionnels), OBS-6 (logs LLM exigés
§5.4), DOC-4 (checklist de remise) — ce sont des points de contrôle explicitement notés.
