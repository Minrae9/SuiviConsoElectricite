$ErrorActionPreference = "Stop"

# Racine du projet = dossier parent de "scripts"
$projectRoot = Split-Path -Path $PSScriptRoot -Parent
$batchPath = Join-Path -Path $projectRoot -ChildPath "run_scraper.bat"

if (-not (Test-Path -LiteralPath $batchPath)) {
    exit 1
}

# Force un scraping totalement invisible, meme si config/.env contient MINT_HEADLESS=false.
$env:MINT_HEADLESS = "true"

Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$batchPath`"" -WindowStyle Hidden -WorkingDirectory $projectRoot -Wait

# Pousser les données mises à jour vers GitHub
try {
    Push-Location -Path $projectRoot
    $status = & git status --porcelain -- data/conso_processed.json data/conso_raw.json 2>&1
    if ($status) {
        & git add data/conso_processed.json 2>&1
        & git commit -m "Auto-update data $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1
        & git push 2>&1
    }
    Pop-Location
} catch {
    # Silencieux - on ne bloque pas si le push échoue
}