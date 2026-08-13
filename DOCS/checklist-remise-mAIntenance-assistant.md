# Checklist de remise — DOC-4

## 1. 8 livrables attendus

1. README complet avec architecture, choix techniques, limites et instructions de lancement.
2. Rapport technique synthétique couvrant l’approche, le RAG, les outils, l’évaluation, la sécurité et les limites.
3. Backend fonctionnel avec API FastAPI et orchestrateur complet.
4. Frontend de démonstration Streamlit exploitable en local.
5. Fichier de lancement `run.sh` / `run.ps1` prêt à exécuter le projet.
6. Résultats d’évaluation consolidés dans `backend/tests/eval_results.json`.
7. Traces d’observabilité JSONL générées par les appels LLM, outils et tickets traités.
8. Dossier de démonstration final comprenant scénarios, ordre de passage et notes de discours.

## 2. 4 scénarios de démonstration obligatoires

1. Incident courant : imprimante qui n’imprime plus.
2. Incident urgent : serveur de production injoignable / équipe bloquée.
3. Demande incomplète : ticket vague, système demande des informations manquantes.
4. Demande sensible : tentative de réinitialisation de mot de passe sans vérification d’identité.

### Vérification attendue

- 1 : résolution ou action ciblée, réponse structurée, sans validation humaine inutile.
- 2 : escalade ou réponse de priorisation élevée, avec diagnostic rapide et priorisation claire.
- 3 : demande de complétude, questions ciblées, pas de réponse “à l’aveugle”.
- 4 : blocage immédiat ou escalade sécurité, avec validation humaine avant aucune exécution.

## 3. 3 points de contrôle avant remise

1. Démarrage sans erreur : `run.sh` / `run.ps1` lance API + frontend, `.env` présent, clé Gemini configured.
2. Trajectoire fonctionnelle : API répond, frontend appelle `/tickets/traiter`, et `/observabilite/traces` retourne des traces.
3. Contrôle qualité : sécurité active, résultats d’évaluation disponibles, pas de sortie non conforme ni d’action exécutée sans approbation humaine.

## 4. Vérification finale

Avant de clôturer la remise, vérifier impérativement :

- le README correspond au code réellement livré ;
- le rapport technique ne promulgue pas d’éléments non implémentés ;
- la démo suit les scénarios attendus dans l’ordre prévu ;
- les logs et traces sont présents et lisibles ;
- la remise reste cohérente avec les résultats mesurés et les limites connues.

## 5. Recommandation de remettre en pratique

Il est préférable de lancer un contrôle “pre-flight” de 5 minutes avant la démonstration :

- vérifier la santé de l’API ;
- tester le scénario 1 et 4 ;
- vérifier que les logs sont bien écrits ;
- confirmer qu’une action sensible demande validation humaine.
