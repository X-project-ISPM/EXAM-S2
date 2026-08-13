"""Sortie structurée — robustesse de la décision finale (OUT-2/OUT-3).

Deux garanties du §5.3 du sujet (« les décisions importantes doivent respecter
un schéma défini ») :

1. `generer_avec_retry()` : quand un LLM produit une sortie non conforme au
   schéma, on ne l'accepte jamais telle quelle et on ne crashe pas non plus —
   on régénère une fois avec le message d'erreur de validation intégré au
   prompt (« ta réponse précédente ne respectait pas le schéma : ... »),
   puis on abandonne proprement si l'échec persiste.

2. `reponse_erreur_controlee()` : quoi qu'il arrive (timeout API, quota, sortie
   non conforme), l'orchestrateur peut toujours construire un `TicketDecision`
   valide en escalade — jamais une erreur nue vers l'utilisateur (§2 de
   l'architecture, gestion d'erreurs).
"""

from pydantic import BaseModel, ValidationError

from src.config import config
from src.schemas import TicketDecision


def generer_avec_retry(
    prompt_fn,
    schema: type[BaseModel],
    max_essais: int | None = None,
) -> BaseModel:
    """Génère une sortie conforme au schéma, avec une régénération sur échec.

    `prompt_fn` est le fournisseur de la génération : il reçoit
    `erreur_precedente` (None au 1er essai, le message de ValidationError
    ensuite) et retourne l'objet à valider. C'est lui qui sait intégrer le
    message dans le prompt — classification, diagnostic et RAG partagent ainsi
    la même stratégie sans la dupliquer.

    Lève `RuntimeError` si toutes les tentatives échouent : l'orchestrateur
    (ORCH-3) la dégrade en `reponse_erreur_controlee()`.
    """
    essais = max_essais or config.llm_max_essais_validation
    derniere_erreur: ValidationError | None = None

    for _ in range(essais):
        try:
            brut = prompt_fn(erreur_precedente=derniere_erreur)
            return schema.model_validate(brut)
        except ValidationError as e:
            derniere_erreur = e

    raise RuntimeError(
        f"Échec de génération conforme à {schema.__name__} "
        f"après {essais} essais. "
        f"Dernière erreur de validation : {derniere_erreur}"
    ) from derniere_erreur


def reponse_erreur_controlee(description: str, message_erreur: str) -> TicketDecision:
    """Décision de repli, toujours valide : jamais d'erreur nue.

    Retourne une escalade avec validation humaine requise, confiance nulle et
    le motif technique dans le diagnostic — l'utilisateur sait que le système
    n'a pas pu traiter son ticket, et un humain le reprend.
    """
    return TicketDecision(
        resume=(description or "Ticket non traité")[:200],
        categorie="autre",
        priorite="haute",
        equipe="support_niveau_1",
        confiance=0.0,
        informations_manquantes=[],
        diagnostic=f"Erreur technique, ticket transmis à un opérateur : {message_erreur}",
        etapes_resolution=[],
        sources=[],
        outils_utilises=[],
        action="escalade",
        validation_humaine_requise=True,
    )
