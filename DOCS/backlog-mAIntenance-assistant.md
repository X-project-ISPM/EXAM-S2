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
| ~~DIAG-1~~ ✅ | Prompt d'extraction, avec interdiction explicite d'inventer ou de recopier | 25 min | SETUP-4 |
| ~~DIAG-2~~ ✅ | `extraire_diagnostic(description, categorie)` — extraction LLM + manques calculés en code | 20 min | DIAG-1 |
| ~~DIAG-3~~ ✅ | `generer_questions()` — tri par priorité, plafond à 2, reformulation par catégorie | 20 min | DIAG-2 |
| ~~DIAG-4~~ ✅ | Scénario 3 vérifié sur cas réels + 4 tests réseau | 20 min | DIAG-3 |

**Revue de code — 5 défauts trouvés et corrigés :**
1. *Le module ne s'importait pas du tout* : `from schemas import …` au lieu de
   `from src.schemas import …`. `diagnostic.py` était du code mort, inutilisable par
   l'orchestrateur.
2. *Même régression dans `llm_client.py`* (`from config import config`) — celle-là cassait
   **tout le projet**, ce module étant importé par classifier, rag, agent et sortie. Cause
   racine commune : des fichiers exécutés directement depuis `src/`, où les imports nus
   fonctionnent par accident.
3. *Règle métier confiée au LLM* : le prompt demandait au modèle de juger quels champs
   étaient « nécessaires pour ce type de problème ». Les questions posées à l'utilisateur
   variaient donc d'un appel à l'autre pour un même ticket. La table
   `CHAMPS_REQUIS_PAR_CATEGORIE` tranche désormais en code — et la catégorie est déjà
   connue, puisque la classification tourne avant.
4. *Fichier de test dans `src/`*, exécutant de vrais appels LLM au simple import — donc
   jamais collecté par pytest, et dangereux pour quiconque importait le paquet. Déplacé en
   `tests/test_diagnostic.py`, réécrit en tests pytest (27 hors-ligne + 4 réseau).
5. *Champs remplis par supposition* : rien n'interdisait au modèle d'inventer. Un champ
   inventé passe pour renseigné, la question n'est jamais posée, et le diagnostic se fait
   sur une base fausse.

**Défaut trouvé en exécution réelle** : sur « Ça ne marche plus », le modèle recopiait le
ticket mot pour mot dans `symptomes`. Le champ paraissait renseigné, aucune question
n'était posée — **le scénario 3 obligatoire ne se déclenchait pas**. Corrigé par une
vérification déterministe (`_est_un_echo`) qui écarte tout champ ne faisant que redire le
ticket, accents et ponctuation repliés.

**Conservé du travail initial** : la priorisation des questions par `PRIORITE_CHAMPS`,
meilleure que le `[:2]` naïf du document d'architecture — l'ordre des champs manquants
suit la déclaration du schéma, pas leur utilité.

## 📚 RAG

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| ~~RAG-1~~ ✅ | ChromaDB persistant + embeddings, **en espace cosinus explicite** | 20 min | SETUP-1 |
| ~~RAG-2~~ ✅ | Chunking respectant les frontières de phrase, avec chevauchement | 30 min | — |
| ~~RAG-3~~ ✅ | Ingestion (corpus d'amorçage : 15 articles → 15 fragments) | 30 min | RAG-1, RAG-2 |
| ~~RAG-4~~ ✅ | `retrieve_context()` — catégorie en orientation, jamais en filtre dur | 30 min | RAG-3 |
| ~~RAG-5~~ ✅ | Prompt de génération avec citations obligatoires | 25 min | SETUP-4 |
| ~~RAG-6~~ ✅ | Drapeau `incertain` + contrôle déterministe des sources citées | 20 min | RAG-4, RAG-5 |
| ~~RAG-7~~ ✅ | Seuil calibré par balayage mesuré (`tests/calibrer_seuil.py`) | 20 min | RAG-4 |
| ~~RAG-8~~ ✅ | `eval_rag.json` : 15 questions couvertes + 5 hors corpus | 30 min | RAG-3 |
| ~~RAG-9~~ ✅ | `evaluer_rag()` — rappel@k, précision des citations, rejet hors-corpus | 25 min | RAG-8 |

**Résultats mesurés** (24 articles, 34 questions dont 8 hors corpus) : rappel@k **96 %**,
précision des citations **100 %**, détection « pas de source » **100 %**.

**Revue de code — 3 défauts trouvés et corrigés :**
1. *Chevauchement dégénéré* : avec un chevauchement supérieur à la taille du fragment,
   chaque fragment repartait presque du début du précédent — taille croissant sans fin et
   contenu dupliqué **×4,8** dans l'index. Le chevauchement est désormais borné à la
   moitié de la taille du fragment.
2. *Ingestion non idempotente* : `add` laissait silencieusement l'ancienne version d'un
   article réindexé. Or les articles portent une date de mise à jour et sont censés
   évoluer en cours de journée. Remplacé par `upsert`.
3. *Filtre dur par catégorie* : rendait la bonne procédure inatteignable quand la
   classification se trompait. La catégorie oriente désormais la recherche au lieu de la
   restreindre.

**Optimisations** : appels `count()` redondants supprimés (3 → 1 par recherche) ;
plafond de fragments par source pour qu'un article long ne monopolise pas le top-k ;
`k` porté de 4 à 8 sur mesure (rappel 92 % → 96 %, stagne au-delà).

**Quatre découvertes qui ont changé la conception :**
1. *ChromaDB indexe en **L2 au carré**, pas en cosinus* (vérifié : distance 2.0 pour des
   vecteurs orthogonaux, pas 1.0). Le seuil « 0.35 cosinus » du document d'architecture
   se serait appliqué à une échelle double. La collection est créée en `hnsw:space:
   cosine` explicitement.
2. *Le seuil de 0.35 donnait **0 % de rappel***. Les bonnes sources sont à une distance
   de 0.36 à 0.59 : le RAG aurait répondu « aucune source » à absolument tout.
3. *Aucun seuil ne peut séparer le hors-corpus.* Sur le corpus élargi les plages se
   chevauchent nettement : la meilleure correspondance d'une question hors corpus
   descend à 0.49, sous plusieurs bonnes réponses — **marge de séparation négative**
   (−0.10). Le garde-fou porteur est donc le drapeau `incertain` de la génération,
   mesuré à 100 % de détection, y compris sur trois pièges conçus pour provoquer une
   recombinaison de sources partielles.
4. *Le modèle multilingue n'apporte rien ici* : même rappel sur le pipeline réel, mais
   marge de séparation deux fois plus mauvaise (−0.38) et deux fois plus de couches.
   Hypothèse de départ invalidée par la mesure, malgré un corpus francophone.

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
| ~~SEC-1~~ ✅ | `MOTS_CLES_INJECTION` (6 motifs) + `PATTERN_ROLE_SYSTEME` en début de ligne + `check_injection()` | 25 min | — |
| ~~SEC-2~~ ✅ | `OUTILS_SENSIBLES` et `est_sensible()` — dans `tools.py`, réexportés par `guardrails.py` | 15 min | AGT-1 |
| ~~SEC-3~~ ✅ | `escalade_immediate()` — `TicketDecision` valide, aucun outil appelé, aucune procédure générée | 20 min | SEC-1, OUT-1 |
| ~~SEC-4~~ ✅ | `verifier_intention_malveillante_llm()` fusionnée dans `check_injection()` (OU logique) | 30 min | SEC-1, SETUP-4 |
| SEC-5 ⏳ | `masquer_donnees_sensibles()` / `masquer_objet()` écrits et testés dans `guardrails.py` ; **reste à brancher** dans OBS-1 et OBS-6, qui n'existent pas encore | 15 min | OBS-1, OBS-6 |
| ~~SEC-6~~ ✅ | Scénario 4 testé avec 3 formulations qui contournent les mots-clés + 2 tickets légitimes en contrôle inverse (`pytest -m reseau`) | 25 min | SEC-3, SEC-4, AGT-6 |

**Résultats mesurés** (`pytest tests/test_guardrails.py`, 38 tests hors réseau + 5 réels
sur `gemini-3.5-flash-lite`) : les 3 attaques reformulées du scénario 4 passent la couche
mots-clés et sont **toutes rattrapées par la couche LLM** ; les 2 tickets légitimes qui
parlent de sécurité (phishing, compte verrouillé) ne sont **pas** signalés.

**Répartition du travail entre les deux couches** — la couche 1 est réglée pour la
**précision**, la couche 2 porte le **rappel**. Trois motifs candidats ont été retirés
après avoir produit des faux positifs sur des tickets de support plausibles :
`sans restriction` (« un accès sans restriction au dossier partagé compta »),
`mode développeur` (« j'ai activé le mode développeur de Chrome »), `jailbreak`
(« mon téléphone a été jailbreaké » — vrai ticket de cybersécurité). Ces cas sont
verrouillés par un test de non-régression. Même logique pour `PATTERN_ROLE_SYSTEME`,
limité à l'anglais : `Système : Windows 11` est un en-tête de ticket ordinaire.

**Trois décisions prises pendant l'implémentation :**
1. *La couche 2 est court-circuitée quand la couche 1 a détecté.* Le verdict étant un OU
   logique, l'appel LLM ne pourrait pas changer le résultat — il coûterait une requête
   sur les ~15/minute du Free Tier sans rien apporter. Vérifié par test (zéro appel).
2. *Échec LLM = dégradation sur la couche 1, pas blocage du ticket.* Bloquer serait
   illusoire : si le modèle est injoignable, la classification et le RAG le sont aussi et
   ORCH-3 dégrade de toute façon. Le fait que la vérification n'ait pas eu lieu reste
   visible dans le champ `verification_llm` de la trace.
3. *Le masquage ne s'applique qu'au couple étiquette + valeur.* Un `if "mot de passe" in
   texte` aurait masqué « j'ai oublié mon mot de passe » — un log exact mais devenu
   inexploitable pour le support. Une liste de suites non secrètes (`expiré`, `refusé`,
   `oublié`...) protège les cas où la valeur n'en est pas une.

**Écart assumé avec le §9 de l'architecture** : `escalade_immediate()` construit
`categorie="cybersecurite"` / `equipe="securite_si"` là où le pseudo-code écrit
`categorie="autre"` / `equipe="securite"`. `"securite"` n'existe pas dans le vocabulaire
`Equipe` de `schemas.py` (la décision aurait été rejetée par Pydantic), et `"autre"`
route vers le support de niveau 1 — soit la mauvaise équipe pour une tentative de
manipulation.

**Reste à faire (hors périmètre du bloc)** : ORCH-1 doit appeler `check_injection()` puis
`escalade_immediate()` **avant** la classification (§2 de l'architecture) ; OBS-1/OBS-6
doivent passer leurs entrées par `masquer_objet()` avant écriture.

## 📊 Observabilité

| ID | Ticket | Estimation | Dépendances |
|---|---|---|---|
| ~~OBS-1~~ ✅ | `log_trace()` et `log_tool_call()` (écriture JSONL), + lecteurs `lire_dernieres_traces()`/`lire_derniers_appels_outils()` | 30 min | OUT-1 |
| OBS-2 | Brancher les logs à chaque étape de l'orchestrateur | 20 min | OBS-1 ✅, ORCH-1 |
| ~~OBS-3~~ ✅ | `estimer_cout()` (approximatif, tarifs configurables) | 20 min | OBS-1 |
| ~~OBS-4~~ ✅ | Endpoint `GET /observabilite/traces` — branché sur le stub SETUP-5 dès maintenant, données réelles pour FE-6 sans attendre ORCH-1 | 15 min | OBS-1 |
| OBS-5 | Décomposer la latence par étape (classification/RAG/agent) dans chaque trace | 20 min | OBS-2 |
| ~~OBS-6~~ ✅ **[NOUVEAU]** | `log_llm_call()` (écrit dans `logs/llm_calls.jsonl`), branché dans `llm_call()`/`llm_call_with_tools()` via un hook (`set_log_llm_call`, même pattern que `tools.set_log_appel` — import direct impossible, cycle via `guardrails.py`) | 25 min | OBS-1 ✅, SETUP-4 |

**Résultats mesurés** : suite complète 204 tests, `ruff` clean. Testé en réel avec un serveur uvicorn (pas juste `TestClient`) : `POST /tickets/traiter` puis `GET /observabilite/traces` retournent bien la trace écrite sur disque, secrets masqués (`Ete2024!` → `***`) dans la description et la décision imbriquée.

**Bug trouvé et corrigé en cours de route (dans `guardrails.py`, hors périmètre OBS)** : `masquer_objet()` masquait `tokens_entree`/`tokens_sortie` (compteurs numériques d'OBS-6) parce que « token » y apparaît en sous-chaîne. Un `\b` autour du motif aurait aussi empêché de masquer des clés composées légitimes comme `user_token` (le soulignement n'est pas une frontière de mot). Fix ciblé : `token(?!s_)` — exclut seulement la forme plurielle suivie d'un underscore, sans affaiblir la détection ailleurs. Tests de régression ajoutés dans `test_guardrails.py`.

**Portée non couverte ici (attend ORCH-1)** : OBS-2 et OBS-5 nécessitent que l'orchestrateur réel existe pour propager `trace_id`/latences par étape jusqu'à `llm_call()`. `log_llm_call()` accepte déjà `etape`/`trace_id` en paramètres optionnels — aucun appelant existant (classification, diagnostic, RAG, agent, garde-fous) n'a besoin d'être modifié quand ORCH-1 les branchera.

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
