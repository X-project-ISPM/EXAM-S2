# Fichier de lancement Windows (équivalent de run.sh).
# Démarre l'API FastAPI en arrière-plan puis Streamlit au premier plan ;
# l'API est arrêtée quand on quitte Streamlit.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Error "`.env` absent. Copier .env.example vers .env et y renseigner GEMINI_API_KEY (https://aistudio.google.com/apikey)."
    exit 1
}

$racine = $PSScriptRoot
$python = Join-Path $racine ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# `src` n'est importable que depuis backend/ (restructuration pour le
# déploiement) : lancer depuis la racine échoue en ModuleNotFoundError.
# -WorkingDirectory ne change que le cwd du process enfant, pas celui de ce
# script (donc les chemins ci-dessous restent résolus depuis $racine).
$api = Start-Process -FilePath $python -ArgumentList "-m","uvicorn","src.api:app","--port","8000" `
    -WorkingDirectory (Join-Path $racine "backend") -PassThru -NoNewWindow
try {
    Start-Sleep -Seconds 2
    # Sans ceci, frontend/app.py retombe sur son défaut (l'instance déployée
    # sur Render) au lieu de l'API locale démarrée ci-dessus — confirmé en
    # réel : l'API locale ne recevait aucune requête tant que cette variable
    # n'était pas positionnée.
    $env:API_URL = "http://localhost:8000"
    & $python -m streamlit run (Join-Path $racine "frontend\app.py") --server.port 8501
}
finally {
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
