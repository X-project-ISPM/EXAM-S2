#!/bin/bash
# Fichier de lancement (livrable n°2 du sujet).
# Démarre l'API FastAPI puis l'interface Streamlit, et arrête proprement
# les deux processus à la sortie (Ctrl-C).
set -e

cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "ERREUR : .env absent. Copier .env.example vers .env et y renseigner GEMINI_API_KEY."
    echo "Clé à générer sur https://aistudio.google.com/apikey"
    exit 1
fi

RACINE="$(pwd)"
PYTHON="$RACINE/.venv/Scripts/python.exe"
[ -x "$PYTHON" ] || PYTHON="$RACINE/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python"

# `src` n'est importable que depuis backend/ (restructuration pour le
# déploiement) : lancer depuis la racine échoue en `ModuleNotFoundError`.
(cd "$RACINE/backend" && "$PYTHON" -m uvicorn src.api:app --port 8000) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

sleep 2
"$PYTHON" -m streamlit run "$RACINE/frontend/app.py" --server.port 8501
