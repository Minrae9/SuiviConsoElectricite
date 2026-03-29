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