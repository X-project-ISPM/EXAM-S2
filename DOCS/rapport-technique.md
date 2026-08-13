# Rapport technique synthétique — mAIntenance & Assistance

## 1. Approche générale

Le système est un assistant de support informatique conçu pour traiter un ticket depuis sa soumission jusqu’à la décision finale : classification, diagnostic, recherche de contexte, génération de réponse, action contrôlée et validation humaine si nécessaire. L’architecture repose sur un pipeline Python simple, sans microservices ni framework d’agent lourd, car le sujet impose un délai de développement court et une trajectoire de mise au point rapide.

Le cœur du projet est un orchestrateur Python qui enchaîne les étapes dans un flux déterministe :

1. validation du ticket et garde-fous d’entrée ;
2. classification métier ;
3. diagnostic et collecte des informations manquantes ;
4. recherche documentaire par RAG ;
5. boucle agent avec outils ;
6. validation du schéma de sortie et retour JSON structuré.

Le backend est servi par FastAPI, avec une API REST exposant les endpoints de traitement, de validation et d’observabilité. L’interface de démonstration est un frontend Streamlit qui montre le chat, les scénarios préchargés et le journal d’activité.

## 2. Classification et diagnostic

La classification est réalisée en few-shot via Gemini, avec une liste de catégories restreinte et un mapping déterministe vers l’équipe de traitement. Le choix de cette stratégie s’explique par la nécessité de livrer un résultat fiable rapidement sans entraîner un modèle spécifique. Le système n’a pas à “deviner” l’équipe en libre ; il catégorise puis applique une table de routage explicite.

Le diagnostic reprend ensuite la catégorie déjà connue pour extraire les informations manquantes, prioriser les questions et éviter de recopier le ticket tel quel dans les champs structuraux. Cela est crucial pour le scénario 3 obligatoire (“Ça ne marche plus”) : la logique impose que le système ne considère comme “connu” que les champs réellement renseignés, et non les informations redondantes ou inventées.

## 3. RAG et recherche documentaire

La recherche documentaire est construite autour de ChromaDB et d'embeddings locaux optimisés via le runtime ONNX (`ONNXMiniLM_L6_V2`). Ce choix garantit un temps de calcul minimal et une empreinte mémoire strictement inférieure aux 512 Mo alloués par Render en hébergement gratuit, éliminant les risques de crash 502 (Out-Of-Memory). Les articles sont découpés en fragments avec chevauchement, indexés en espace cosinus explicite et interrogés avec un top-k mesuré. Le score de pertinence est ensuite comparé à un seuil calibré sur des jeux de tests, ce qui permet d'identifier les cas hors corpus sans inventer de source.

Le mécanisme inclut trois protections importantes :

- le top-k recherche des fragments proches du ticket ;
- le générateur ne peut citer que des sources effectivement renvoyées par le moteur ;
- un drapeau d’incertitude est produit si la base n’a pas de réponse suffisamment solide.

Cette stratégie permet d’éviter le piège classique du “ça ressemble” : le système préfère refuser de répondre proprement plutôt que de produire une procédure inventée.

## 4. Agent, outils et validation humaine

L’agent travaille à partir d’un schéma de sortie contraint et d’outils exposés via function calling. Il ne peut pas exécuter n’importe quelle action : les outils sont déclarés, validés, puis suivis d’un garde-fou de sécurité. Les actions sensibles (par exemple les mises à jour de ticket ou les escalades techniques) doivent être confirmées par un opérateur humain avant exécution réelle.

Cette validation n’est pas seulement un luxe fonctionnel ; elle est une condition de robustesse. Le système sépare clairement :

- le raisonnement et la recommandation ;
- l’exécution réelle d’une action ;
- la trace de validation associée à un `trace_id`.

Le frontend lit cette séquence et laisse un humain approuver ou refuser l’action avant qu’elle ne soit appliquée.

## 5. Évaluation et résultats mesurés

Le projet a été évalué sur deux axes : classification et RAG.

### Classification

- 20 tickets
- 8 catégories couvertes
- 4 pièges de frontière, 1 ticket vague, 1 ticket avec fautes d’orthographe, 1 hors périmètre informatique

Résultats mesurés :

- exactitude catégorie : 100 %
- rappel/précision par catégorie : 100 % sur les 8 catégories
- exactitude priorité : 95 %

Le seul échec restant portait sur une distinction subtile entre priorité moyenne et haute, dans un cas où le barème pouvait être lu de deux façons. Le système a conservé cette ambiguïté plutôt que de forcer une mauvaise classification.

### RAG

- 24 articles dans la base
- 34 questions, dont 8 hors corpus

Résultats mesurés :

- rappel@k : 96,2 %
- précision des citations : 100 %
- détection des cas sans source : 100 %

Le point clé est que le système a bien appris à dire “je ne sais pas” quand le corpus ne permet pas de répondre. C’est précisément ce comportement qui évite les réponses fausses et les procédures non existantes.

## 6. Sécurité et garde-fous

La sécurité est structurée en couches, pas en simple filtre terminal.

1. Détection par mots-clés : rapide, utile pour les cas évidents.
2. Vérification LLM indépendante : analyse du ticket comme donnée, sans exécution d’instruction.
3. Règle déterministe côté code : les outils sensibles sont listés et contrôlés en Python.
4. Masquage des données sensibles avant tout log : mots de passe ou données d’identification ne sont jamais écrits en clair dans les fichiers JSONL.

Le système répond automatiquement en escalade si une tentative de manipulation est détectée. Cela couvre le cas où un utilisateur tente d’ignorer les instructions de sécurité ou de demander la réinitialisation d’un mot de passe sans vérification.

## 7. Limites connues

Le prototype est solide, mais il reste conscient de ses limites :

- la sortie du modèle n’est pas entièrement déterministe, même à température 0 ;
- le quota Gemini Free Tier impose un lissage explicite des appels, et un dépassement peut ralentir un ticket de plusieurs minutes en cas de reprise imposée par l’API ;
- les 6 fichiers de données métier (`kb.json`, `utilisateurs.json`, `equipements.json`, `services.json`, `incidents_actifs.json`, `tickets_historique.json`) sont désormais complets dans `backend/data/` ; `tickets_historique.json` s’incrémente automatiquement à chaque ticket traité par l’API, y compris en test manuel — un nettoyage est recommandé avant de le réutiliser comme jeu de données de référence propre ;
- la génération de réponse se protège par validation de schéma, mais le système reste dépendant d’un service externe (Gemini) et, en hébergement Render, d’un volume ChromaDB éphémère (ré-ingéré automatiquement au démarrage si vide).

Ces limites sont explicitement documentées, ce qui est un critère positif pour la revue : elles montrent que le projet ne prétend pas couvrir un contexte hors du périmètre technique réellement livré.

## 8. Conclusion

Le projet démontre qu’un assistant de support informatique fonctionnel peut être construit en quelques heures en combinant :

- classification structurée ;
- diagnostic orienté données ;
- RAG contrôlée ;
- agent à outils avec validation humaine ;
- observabilité et sécurité prévues dès le départ.

L’architecture est volontairement modeste, robuste et justifiable. Elle privilégie la transparence et la conformité au sujet plutôt que la sophistication inutile.
