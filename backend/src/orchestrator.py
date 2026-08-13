"""Orchestrateur du pipeline de traitement d'un ticket (ORCH-1 / ORCH-3).

Enchaîne les cinq étapes du §2 de l'architecture — garde-fous, classification,
diagnostic, RAG, agent — et applique en sortie les règles métier qui ne peuvent
pas être confiées au modèle.

Deux principes structurent ce module :

1. **Une seule étape est bloquante.** Sans classification, il n'y a rien à
   router ni à diagnostiquer : son échec produit une réponse dégradée
   immédiate. Diagnostic, RAG et agent sont *optionnels* — leur indisponibilité
   dégrade la décision (moins de contexte, escalade, validation humaine) au
   lieu d'interrompre le traitement. Un `try/except` unique autour de tout le
   pipeline, comme dans le pseudo-code, transformerait une panne du RAG en
   « erreur technique » alors que la classification, elle, avait réussi.

2. **Le dernier mot revient au code, pas au modèle.** Catégorie et équipe
   viennent de la classification (routage déterministe, CLASS-2), la priorité
   ne peut qu'être relevée par l'agent, les sources citées sont recoupées avec
   les passages réellement fournis, et les questions à l'utilisateur sont
   celles de DIAG-3. L'agent propose une décision ; l'orchestrateur la
   contresigne.

`traiter_ticket()` ne lève jamais : toute sortie est un `TicketDecision`
valide (§5.3 du sujet, gestion d'erreurs du §2).
"""

import logging
import time
import uuid
from typing import Any

from src.agent import run_agent
from src.classifier import classify_ticket, router_vers_equipe
from src.config import config
from src.diagnostic import extraire_diagnostic, generer_questions
from src.guardrails import (
    categorie_sensible,
    check_injection,
    escalade_immediate,
    masquer_donnees_sensibles,
)
from src.rag import retrieve_context
from src.schemas import (
    PRIORITES,
    Classification,
    DiagnosticInfo,
    TicketDecision,
    TicketInput,
    TicketReponse,
)
from src.sortie import reponse_erreur_controlee

logger = logging.getLogger(__name__)


# --- Hook d'observabilité (OBS-2) --------------------------------------------
# Même mécanisme que `tools.set_log_appel` : l'orchestrateur ne dépend pas d'un
# module d'observabilité qui n'existe pas encore, et OBS-2 se branche sans
# toucher au pipeline.

_log_trace: Any = None


def set_log_trace(fonction) -> None:
    """Branche l'écriture des traces (OBS-2). Signature attendue, reprise du
    §2 de l'architecture :
    `fonction(trace_id, ticket, classification, contexte, decision, latence_ms)`.
    """
    global _log_trace
    _log_trace = fonction


# --- Budget de temps (ORCH-3) ------------------------------------------------


def _budget_epuise(depart: float) -> bool:
    return (time.monotonic() - depart) > config.orchestrateur_budget_s


def _etape_optionnelle(nom: str, fonction, defaut, depart: float) -> tuple[Any, str | None]:
    """Exécute une étape dont l'échec dégrade la décision sans l'interrompre.

    Retourne `(resultat, degradation)` : `degradation` est None si l'étape a
    réussi, sinon une phrase courte destinée au diagnostic et aux logs.
    """
    if _budget_epuise(depart):
        return defaut, f"{nom} sautée (budget de {config.orchestrateur_budget_s:.0f} s dépassé)"
    try:
        return fonction(), None
    except Exception as e:  # noqa: BLE001 — aucune étape optionnelle ne doit faire échouer le ticket
        logger.warning("Étape « %s » indisponible : %s", nom, e)
        return defaut, f"{nom} indisponible ({type(e).__name__})"


# --- Règles métier appliquées à la décision de l'agent -----------------------


def _priorite_max(classification: str, agent: str) -> str:
    """Retourne la plus haute des deux priorités.

    L'agent voit ce que la classification ignore — un incident global remonté
    par `rechercher_incidents_actifs` justifie de passer en critique. L'inverse
    n'est pas vrai : rien de ce qu'il découvre ne peut rendre un ticket moins
    urgent que ce que sa description montrait déjà, et le laisser abaisser la
    priorité ouvrirait la porte à une désescalade suggérée par le ticket
    lui-même.
    """
    return max(classification, agent, key=PRIORITES.index)


def _contexte_agent(ticket: TicketInput) -> str:
    """Texte passé à l'agent : la description, plus l'identifiant utilisateur
    s'il est fourni.

    Ajouté ici et pas en amont : la classification et le diagnostic doivent
    voir exactement ce que l'utilisateur a écrit, alors que l'agent a besoin de
    l'identifiant pour appeler `rechercher_utilisateur`.
    """
    if not ticket.utilisateur_id:
        return ticket.description
    return f"{ticket.description}\n\n[Métadonnée] utilisateur_id : {ticket.utilisateur_id}"


def _decision_sans_agent(
    ticket: TicketInput,
    classification: Classification,
    diagnostic: DiagnosticInfo | None,
    motif: str,
) -> TicketDecision:
    """Décision construite quand l'agent n'a pas pu conclure.

    Conserve tout ce qui a déjà été obtenu — catégorie, priorité, équipe,
    confiance de la classification — au lieu de retomber sur
    `reponse_erreur_controlee()`, qui route tout vers le support de niveau 1
    en « autre ». Un ticket réseau critique reste un ticket réseau critique,
    même quand l'agent est indisponible.

    `motif` est masqué (SEC-5) avant d'entrer dans le diagnostic : c'est
    souvent un message d'exception qui peut recopier un extrait brut de
    réponse LLM, potentiellement du texte du ticket lui-même.
    """
    return TicketDecision(
        resume=masquer_donnees_sensibles(ticket.description)[:200],
        categorie=classification.categorie,
        priorite=classification.priorite,
        equipe=classification.equipe,
        confiance=classification.confiance,
        informations_manquantes=[],
        diagnostic=(
            "Le ticket a été classé, mais la résolution automatique n'a pas abouti "
            f"({masquer_donnees_sensibles(motif)}). Il est transmis en l'état à "
            f"l'équipe {classification.equipe}."
        ),
        etapes_resolution=[],
        sources=[],
        outils_utilises=[],
        action="escalade",
        validation_humaine_requise=True,
    )


def _appliquer_regles_metier(
    decision: TicketDecision,
    classification: Classification,
    diagnostic: DiagnosticInfo | None,
    contexte: list[dict],
    degradations: list[str],
) -> TicketDecision:
    """Contresigne la décision de l'agent avec les règles décidées en code."""
    categorie = classification.categorie
    controles = list(degradations)

    # Sources : le modèle ne peut citer que ce qu'on lui a réellement donné.
    # Même contrôle déterministe qu'en RAG-6 — la consigne du prompt ne suffit
    # pas, une référence [KB-XXX] plausible mais inexistante serait citée au
    # technicien comme une procédure officielle.
    disponibles = {fragment["source_id"] for fragment in contexte}
    sources = [s for s in decision.sources if s in disponibles]
    inventees = [s for s in decision.sources if s not in disponibles]
    if inventees:
        controles.append(f"sources absentes du contexte, retirées : {', '.join(inventees)}")

    # Questions à l'utilisateur : règle métier de DIAG-3, pas une production du
    # modèle. Quand le diagnostic a tourné, ses manques font foi.
    informations_manquantes = decision.informations_manquantes
    action = decision.action
    if diagnostic is not None:
        informations_manquantes = generer_questions(
            diagnostic.informations_manquantes, categorie
        )
        # Scénario 3 du sujet : il manque de quoi diagnostiquer, on demande —
        # on ne « résout » pas. L'agent peut proposer une résolution
        # plausible malgré les manques ; c'est précisément ce qu'il ne doit
        # pas faire.
        if informations_manquantes and action == "resolution":
            action = "demande_information"

    confiance = decision.confiance
    if degradations:
        # Une décision produite avec un pipeline amputé ne peut pas afficher la
        # même certitude qu'une décision complète.
        confiance = min(confiance, config.orchestrateur_seuil_confiance)

    # §6 du sujet : validation humaine avant toute action non triviale. Quatre
    # déclencheurs, tous décidés en code — le modèle peut se tromper sur le
    # cinquième champ, il ne peut pas désactiver ceux-là.
    validation_humaine_requise = (
        decision.validation_humaine_requise
        or action == "escalade"
        or categorie_sensible(categorie)
        or confiance < config.orchestrateur_seuil_confiance
        or bool(degradations)
    )

    diagnostic_texte = decision.diagnostic
    if controles:
        diagnostic_texte = f"{diagnostic_texte}\n[Contrôle automatique] {' ; '.join(controles)}."

    return decision.model_copy(
        update={
            "categorie": categorie,
            # Routage déterministe (CLASS-2) : l'équipe n'est jamais reprise du
            # modèle, qui a déjà été vu inventer un nom d'équipe hors
            # vocabulaire.
            "equipe": router_vers_equipe(categorie),
            "priorite": _priorite_max(classification.priorite, decision.priorite),
            "confiance": confiance,
            "informations_manquantes": informations_manquantes,
            "diagnostic": diagnostic_texte,
            "sources": sources,
            "action": action,
            "validation_humaine_requise": validation_humaine_requise,
        }
    )


# --- Pipeline complet (ORCH-1) -----------------------------------------------


def _finaliser(
    trace_id: str,
    ticket: TicketInput,
    classification: Classification | None,
    contexte: list[dict],
    decision: TicketDecision,
    depart: float,
) -> TicketReponse:
    latence_ms = round((time.monotonic() - depart) * 1000)
    if _log_trace is not None:
        try:
            _log_trace(trace_id, ticket, classification, contexte, decision, latence_ms)
        except Exception:  # noqa: BLE001 — une trace illisible ne doit pas faire perdre la décision
            logger.exception("Écriture de trace impossible (trace_id=%s)", trace_id)
    return TicketReponse(trace_id=trace_id, decision=decision)


def traiter_ticket(ticket: TicketInput) -> TicketReponse:
    """Traite un ticket de bout en bout et retourne la décision et sa trace.

    Ne lève jamais : chaque échec possible a une réponse dégradée (ORCH-3).
    """
    trace_id = str(uuid.uuid4())
    depart = time.monotonic()
    degradations: list[str] = []

    # 1. Garde-fous en entrée (SEC-1 + SEC-4), avant toute autre étape : un
    #    ticket qui cherche à manipuler l'assistant ne doit atteindre ni le
    #    classifieur, ni les outils.
    try:
        risque = check_injection(ticket.description)
    except Exception as e:  # noqa: BLE001 — check_injection absorbe déjà LLMError
        logger.exception("Garde-fous d'entrée en échec (trace_id=%s)", trace_id)
        risque = {"danger": False, "raison": None, "couche": None, "verification_llm": "erreur"}
        degradations.append(f"garde-fous d'entrée dégradés ({type(e).__name__})")

    if risque["danger"]:
        decision = escalade_immediate(ticket.description, risque)
        return _finaliser(trace_id, ticket, None, [], decision, depart)

    if risque["verification_llm"] == "indisponible":
        degradations.append("vérification anti-injection LLM indisponible")

    # 2. Classification — seule étape sans laquelle il n'y a rien à exploiter.
    try:
        classification = classify_ticket(ticket.description)
    except Exception as e:  # noqa: BLE001 — jamais de 500 nue vers l'utilisateur
        logger.warning("Classification indisponible (trace_id=%s) : %s", trace_id, e)
        decision = reponse_erreur_controlee(
            ticket.description, f"classification indisponible ({type(e).__name__}) : {e}"
        )
        return _finaliser(trace_id, ticket, None, [], decision, depart)

    # 3. Diagnostic (DIAG-2) puis récupération de contexte (RAG-4) : deux
    #    étapes qui enrichissent la décision sans la conditionner.
    diagnostic, echec = _etape_optionnelle(
        "diagnostic",
        lambda: extraire_diagnostic(ticket.description, classification.categorie),
        None,
        depart,
    )
    if echec:
        degradations.append(echec)

    contexte, echec = _etape_optionnelle(
        "recherche documentaire",
        lambda: retrieve_context(ticket.description, categorie=classification.categorie),
        [],
        depart,
    )
    if echec:
        degradations.append(echec)

    # 4. Agent avec outils (AGT-5).
    if _budget_epuise(depart):
        degradations.append(
            f"agent sauté (budget de {config.orchestrateur_budget_s:.0f} s dépassé)"
        )
        decision = _decision_sans_agent(
            ticket, classification, diagnostic, "budget de temps dépassé"
        )
    else:
        try:
            decision = run_agent(
                _contexte_agent(ticket), classification, diagnostic, contexte, trace_id
            )
        except Exception as e:  # noqa: BLE001 — l'agent échoue, le ticket est quand même traité
            logger.warning("Agent indisponible (trace_id=%s) : %s", trace_id, e)
            degradations.append(f"agent indisponible ({type(e).__name__})")
            decision = _decision_sans_agent(ticket, classification, diagnostic, str(e))

    # 5. Règles métier et contrôles déterministes.
    decision = _appliquer_regles_metier(
        decision, classification, diagnostic, contexte, degradations
    )
    return _finaliser(trace_id, ticket, classification, contexte, decision, depart)
