"""Test de non-régression sur `RACINE` (DOC-4).

Après la restructuration en `backend/`, `RACINE` calculait un niveau de trop
(`parent.parent.parent` au lieu de `parent.parent`) et pointait vers la racine
du dépôt plutôt que `backend/` : `dossier_data`/`dossier_logs`/`dossier_chroma`
visaient tous un chemin inexistant. En silence, puisque `models.py` tolère les
fichiers manquants — `GET /health` répondait `"status": "ok"` avec
`"articles_kb": 0`, la KB, les utilisateurs et l'index Chroma introuvables. Un
bug de chemin, donc invisible aux tests qui construisent leurs propres
`BaseDeDonnees` en mémoire sans jamais lire le disque.
"""

from pathlib import Path

from src.config import RACINE, config


def test_racine_pointe_sur_backend():
    assert RACINE.name == "backend"
    assert RACINE == Path(__file__).resolve().parent.parent


def test_dossiers_de_donnees_existent_reellement():
    """Ancre le test sur le disque, pas seulement sur le calcul du chemin :
    un `RACINE` numériquement correct mais décalé d'un cran ne se détecterait
    pas autrement."""
    assert config.dossier_data.exists()
    assert (config.dossier_data / "kb.json").exists()
    assert config.dossier_logs.exists()
