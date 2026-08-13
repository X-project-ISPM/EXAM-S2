# Fichier de lancement Windows (équivalent de run.sh).
# Démarre l'API FastAPI en arrière-plan puis Streamlit au premier plan ;
# l'API est arrêtée quand on quitte Streamlit.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Error "`.env` absent. Copier .env.example vers .env et y renseigner GEMINI_API_KEY (https://aistudio.google.com/apikey)."
    exit 1
}

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$api = Start-Process -FilePath $python -ArgumentList "-m","uvicorn","src.api:app","--port","8000" -PassThru -NoNewWindow
try {
    Start-Sleep -Seconds 2
    & $python -m streamlit run frontend/app.py --server.port 8501
}
finally {
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
