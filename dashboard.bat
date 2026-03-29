@echo off
setlocal

cd /d "%~dp0"
set "PORT=8080"
set "PYTHON_CMD=python"
set "DASHBOARD_URL=http://localhost:%PORT%/web/index.html?v=%RANDOM%%RANDOM%"

where python >nul 2>&1
if errorlevel 1 (
	where py >nul 2>&1
	if errorlevel 1 (
		echo Python est introuvable. Installez Python ou ajoutez-le au PATH.
		pause
		exit /b 1
	)
	set "PYTHON_CMD=py -3"
)

echo Demarrage du serveur local sur le port %PORT%...
if /i "%PYTHON_CMD%"=="python" (
	start "SuiviConsoElectricite-Server" python -m http.server %PORT%
) else (
	start "SuiviConsoElectricite-Server" py -3 -m http.server %PORT%
)

set "SERVER_READY=0"
for /l %%i in (1,1,20) do (
	powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%DASHBOARD_URL%' -UseBasicParsing -TimeoutSec 1 ^| Out-Null; exit 0 } catch { exit 1 }"
	if not errorlevel 1 (
		set "SERVER_READY=1"
		goto :open_dashboard
	)
	timeout /t 1 /nobreak >nul
)

:open_dashboard
if "%SERVER_READY%"=="1" (
	start "" "%DASHBOARD_URL%"
	echo Le dashboard est ouvert dans votre navigateur.
) else (
	echo Le serveur met plus de temps que prevu a demarrer.
	echo Ouvrez manuellement: %DASHBOARD_URL%
)

echo Pour arreter le serveur, fermez la fenetre "SuiviConsoElectricite-Server".
