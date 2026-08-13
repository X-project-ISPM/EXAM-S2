"""Tests du RAG.

Le découpage et les garde-fous de citation sont testés sans réseau ni index :
ce sont eux qui protègent contre la « génération d'une procédure inexistante »
(§6 du sujet), ils doivent être vérifiables à chaque exécution.
"""

import pytest
from src.rag import ReponseRAG, chunker, generer_reponse_rag

# --- Découpage (RAG-2) ------------------------------------------------------


def test_texte_court_reste_en_un_fragment():
    assert chunker("Une phrase courte. Une autre.", taille_max=200) == [
        "Une phrase courte. Une autre."
    ]


def test_texte_vide_ne_produit_aucun_fragment():
    assert chunker("") == []
    assert chunker("   \n  ") == []


def test_texte_long_est_decoupe():
    texte = " ".join(f"Ceci est la phrase numero {i} du document." for i in range(60))
    fragments = chunker(texte, taille_max=50, chevauchement=10)
    assert len(fragments) > 1


def test_le_decoupage_ne_coupe_pas_au_milieu_d_une_phrase():
    """Une procédure tronquée en plein milieu serait citée incomplète au
    technicien qui l'applique."""
    texte = " ".join(f"Etape numero {i} a realiser avec soin." for i in range(40))
    for fragment in chunker(texte, taille_max=30, chevauchement=5):
        assert fragment.endswith(".")


def test_les_fragments_se_chevauchent():
    """Sans chevauchement, une procédure dont les étapes tombent de part et
    d'autre d'une coupure devient irretrouvable."""
    phrases = [f"Phrase distincte numero {i} avec du contenu." for i in range(40)]
    fragments = chunker(" ".join(phrases), taille_max=40, chevauchement=15)
    fin_premier = fragments[0].split(".")[-2].strip()
    assert fin_premier in fragments[1]


def test_un_chevauchement_excessif_ne_fait_pas_exploser_l_index():
    """Régression : avec un chevauchement supérieur à la taille du fragment,
    chaque nouveau fragment repartait presque du début du précédent. Les
    fragments grossissaient sans fin et le contenu était dupliqué cinq fois
    dans l'index."""
    texte = " ".join(f"Phrase numero {i} ici." for i in range(12))
    fragments = chunker(texte, taille_max=20, chevauchement=30)

    mots_source = len(texte.split())
    mots_indexes = sum(len(f.split()) for f in fragments)
    assert mots_indexes < 2 * mots_source
    assert all(len(f.split()) <= 20 for f in fragments)


def test_tout_le_contenu_est_present_dans_les_fragments():
    texte = " ".join(f"Information capitale numero {i}." for i in range(30))
    fragments = chunker(texte, taille_max=25, chevauchement=5)
    concatenation = " ".join(fragments)
    for i in range(30):
        assert f"Information capitale numero {i}." in concatenation


# --- Absence de source (RAG-6) ----------------------------------------------


def test_aucun_fragment_donne_une_reponse_incertaine_sans_appel_llm(monkeypatch):
    """Sans passage, interroger le LLM l'inviterait à répondre de mémoire —
    précisément le risque de procédure inventée."""

    def interdit(*_args, **_kwargs):
        raise AssertionError("le LLM ne doit pas être appelé sans passage")

    monkeypatch.setattr("src.rag.llm_call", interdit)

    reponse = generer_reponse_rag("une question quelconque", [])
    assert reponse.incertain is True
    assert reponse.sources == []
    assert reponse.etapes_resolution == []


# --- Garde-fou sur les citations --------------------------------------------


@pytest.fixture
def passages():
    return [
        {"source_id": "KB-NET-04", "titre": "Réseau", "contenu": "...", "distance": 0.3},
        {"source_id": "KB-NET-07", "titre": "VPN", "contenu": "...", "distance": 0.4},
    ]


def _simuler_reponse(monkeypatch, **champs):
    valeurs = {
        "diagnostic": "diagnostic simulé",
        "etapes_resolution": ["étape"],
        "sources": [],
        "incertain": False,
    }
    valeurs.update(champs)
    modele = ReponseRAG(**valeurs)
    monkeypatch.setattr("src.rag.llm_call", lambda *a, **k: modele)


def test_sources_valides_sont_conservees(monkeypatch, passages):
    _simuler_reponse(monkeypatch, sources=["KB-NET-04"])
    reponse = generer_reponse_rag("le réseau ne marche plus", passages)
    assert reponse.sources == ["KB-NET-04"]
    assert reponse.incertain is False


def test_source_inventee_est_retiree_et_declenche_l_incertitude(monkeypatch, passages):
    """Le modèle peut produire un identifiant plausible mais absent des
    passages. On ne se fie pas à la consigne du prompt : on vérifie."""
    _simuler_reponse(monkeypatch, sources=["KB-NET-04", "KB-INVENTE-99"])
    reponse = generer_reponse_rag("le réseau ne marche plus", passages)

    assert reponse.sources == ["KB-NET-04"]
    assert reponse.incertain is True
    assert "KB-INVENTE-99" in reponse.diagnostic


def test_toutes_les_sources_inventees_laisse_une_reponse_sans_source(monkeypatch, passages):
    _simuler_reponse(monkeypatch, sources=["KB-FAUX-01", "KB-FAUX-02"])
    reponse = generer_reponse_rag("question", passages)
    assert reponse.sources == []
    assert reponse.incertain is True


# --- Recherche sur index réel -----------------------------------------------


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    """Index isolé, reconstruit dans un dossier temporaire."""
    from src.config import config

    from src import rag

    config.dossier_chroma = tmp_path_factory.mktemp("chroma")
    rag._collection.cache_clear()
    rag.ingerer(rag.charger_kb())
    yield
    rag._collection.cache_clear()


@pytest.mark.index
def test_recherche_retrouve_la_procedure_attendue(index):
    from src.rag import retrieve_context

    fragments = retrieve_context(
        "j'ai oublié mon mot de passe", categorie="comptes_authentification"
    )
    assert "KB-AUTH-01" in {f["source_id"] for f in fragments}


@pytest.mark.index
def test_la_distance_seule_ne_rejette_pas_le_hors_corpus(index):
    """Documente la limite qui justifie l'architecture retenue.

    « politique de remboursement des frais » remonte des passages à une
    distance (~0.57) située dans la plage des bonnes réponses (0.36 à 0.59) :
    aucun seuil ne peut donc séparer le hors-corpus du reste. C'est pourquoi
    le garde-fou porteur est le drapeau `incertain` produit à la génération,
    et non ce seuil. Si ce test venait à échouer parce que plus aucun passage
    ne remonte, le seuil aurait été resserré et le rappel en souffrirait.
    """
    from src.rag import retrieve_context

    fragments = retrieve_context("quelle est la politique de remboursement des frais ?")
    assert fragments, "le seuil ne doit pas être resserré au point de filtrer par distance"


@pytest.mark.index
def test_repli_sans_filtre_quand_la_categorie_est_erronee(index):
    """Si la classification s'est trompée de catégorie, la bonne procédure
    doit rester atteignable — sinon une erreur de classification se propage
    silencieusement en absence de réponse."""
    from src.rag import retrieve_context

    fragments = retrieve_context("j'ai oublié mon mot de passe", categorie="imprimantes")
    assert "KB-AUTH-01" in {f["source_id"] for f in fragments}


@pytest.mark.index
def test_les_distances_respectent_le_seuil(index):
    from src.config import config
    from src.rag import retrieve_context

    fragments = retrieve_context("l'imprimante ne répond plus", categorie="imprimantes")
    assert fragments
    assert all(f["distance"] <= config.rag_seuil_pertinence for f in fragments)


@pytest.mark.index
def test_reingestion_met_a_jour_sans_dupliquer(index):
    """Régression : `add` laissait silencieusement l'ancienne version d'un
    article corrigé dans l'index. Les articles portent une date de mise à
    jour, ils sont donc censés évoluer en cours de journée."""
    from src import rag

    avant = rag.nombre_de_fragments()
    articles = rag.charger_kb()
    articles[0].contenu = "Contenu entierement remplace pour le test de reindexation."

    rag.ingerer(articles, reinitialiser=False)

    assert rag.nombre_de_fragments() == avant, "la réindexation ne doit pas dupliquer"
    fragment = rag._collection().get(ids=[f"{articles[0].id}#0"])["documents"][0]
    assert "entierement remplace" in fragment, "la nouvelle version doit remplacer l'ancienne"

    rag.ingerer(rag.charger_kb())  # restaurer le corpus pour les autres tests


@pytest.mark.index
def test_un_article_long_ne_monopolise_pas_les_resultats(index):
    """KB-PRO-09 est découpé en plusieurs fragments proches les uns des
    autres. Sans plafond par source, ils occuperaient les premières places et
    le modèle ne verrait qu'une seule procédure.

    Le plafond s'applique tant qu'il reste d'autres sources à proposer ; les
    fragments écartés ne servent qu'à compléter jusqu'à k, plutôt que de
    rendre moins de contexte que demandé.
    """
    from src.config import config
    from src.rag import retrieve_context

    question = "comment préparer un poste de travail pour un arrivant"
    fragments = retrieve_context(question, k=4)

    occurrences = sum(1 for f in fragments if f["source_id"] == "KB-PRO-09")
    assert occurrences <= config.rag_max_fragments_par_source
    assert len({f["source_id"] for f in fragments}) >= 2, "le top-k doit croiser les sources"
