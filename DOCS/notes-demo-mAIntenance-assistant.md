# Notes de démo — DOC-5

## Ordre recommandé des scénarios

1. Incident courant : imprimante qui n’imprime plus.
2. Incident urgent : serveur de production injoignable.
3. Demande incomplète : "Ça ne marche plus".
4. Demande sensible : tentative de réinitialisation de mot de passe sans vérification.

Cet ordre permet de faire monter la complexité progressivement : le public voit d’abord un cas standard, puis un cas critique, puis un cas de manque d’information, puis un cas de sécurité.

## Discours de démonstration

### 1. Présentation du système

"Nous avons construit un assistant de support informatique qui traite un ticket de bout en bout : classification, diagnostic, contexte documentaire, agent avec outils, validation humaine et observabilité. L’objectif n’est pas de remplacer l’opérateur, mais de lui donner une décision structurée et de l’aider à agir vite avec moins d’erreurs."

### 2. Scénario 1 — incident courant

"Je lance un ticket classique sur une imprimante qui ne fonctionne plus. Le système classe le problème, identifie la priorité, extrait les informations utiles, cherche la procédure associée dans la base de connaissances et propose une résolution claire."

### 3. Scénario 2 — incident urgent

"Ici, on vérifie la priorisation. Un incident réseau ou infrastructure majeur est détecté comme critique. La réponse ne laisse pas place à l’ambiguïté : la priorité est élevée, l’équipe de route est claire, et l’agent agit avec un raisonnement orienté sécurité et disponibilité."

### 4. Scénario 3 — demande incomplète

"Le système ne se contente pas de répondre au hasard. Quand le ticket est incomplet, il identifie précisément les informations manquantes et demande les détails nécessaires avant d’aller plus loin. C’est là que le diagnostic est utile : il évite les réponses fausses ou les actions sur des hypothèses faibles."

### 5. Scénario 4 — demande sensible

"Le dernier cas montre le point le plus important pour la sécurité. Un message qui demande un accès ou une réinitialisation sans vérification est détecté comme sensible. Le système refuse l’action, escalade et impose la validation humaine avant toute exécution. Cela illustre la chaîne de garde-fous que le projet met en place."

## Points à mettre en avant pendant la démo

- architecture claire et lisible ;
- sortie structurée JSON ;
- RAG avec citations et contrôle des sources ;
- validation humaine sur les actions sensibles ;
- observabilité et traces de chaque ticket ;
- résultats mesurés de classification et de RAG.

## Plan de repli

Si le démonstrateur a un souci réseau ou de quota :

- présenter directement les résultats déjà générés dans les traces et l’évaluation ;
- montrer la sortie JSON du ticket traité ;
- mettre en avant la sécurité et le fait que l’API a bien refusé un scénario sensible ;
- si l’instance déployée (Render) semble en panne, `GET /health/diagnostic?test=gemini` /
  `?test=chromadb` / `?test=data` permet d’identifier en direct le composant fautif (clé
  Gemini, index ChromaDB, fichier de données) plutôt que de deviner devant le jury.

La démonstration doit rester centrée sur la logique métier, pas sur la technologie de l’interface.
