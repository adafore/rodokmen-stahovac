@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Instalator - Rodokmen Stahovac (adafore)

echo ============================================================
echo   INSTALATOR: RODOKMEN STAHOVAC PRO MINI PC (adafore)
echo ============================================================
echo.
echo Tento skript automaticky nainstaluje vse potrebne:
echo   1) Git, Python 3.12 a GitHub CLI (gh)
echo   2) Prihlaseni k tvemu GitHub uctu (adafore)
echo   3) Stazeni repozitare adafore/rodokmen-stahovac do C:\RodokmenStahovac
echo   4) Virtualni prostredi + Playwright + Chromium
echo   5) Zastupce "Spustit_Stahovac.bat" primo na Plochu
echo.
pause

set "INSTALL_DIR=C:\RodokmenStahovac"
set "REPO_URL=https://github.com/adafore/rodokmen-stahovac.git"

:: --- 1. Kontrola a instalace Git ---
where git >nul 2>&1
if errorlevel 1 (
    echo [1/6] Instaluji Git...
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
) else (
    echo [1/6] Git je jiz nainstalovan.
)

:: --- 2. Kontrola a instalace Python ---
where py >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [2/6] Instaluji Python 3.12...
        winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    ) else (
        echo [2/6] Python je jiz nainstalovan.
    )
) else (
    echo [2/6] Python je jiz nainstalovan.
)

:: --- 3. Kontrola a instalace GitHub CLI (gh) ---
where gh >nul 2>&1
if errorlevel 1 (
    echo [3/6] Instaluji GitHub CLI (gh)...
    winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements
) else (
    echo [3/6] GitHub CLI (gh) je jiz nainstalovan.
)

:: Obnoveni PATH v aktualnim okne
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"

:: --- 4. Prihlaseni na GitHub (adafore) ---
echo.
echo [4/6] Kontroluji prihlaseni na GitHub...
gh auth status >nul 2>&1
if errorlevel 1 (
    echo.
    echo Nyni se jednorazove prihlas ke svemu GitHub uctu (adafore).
    echo Otevre se prohlizec nebo se zobrazi 8mistny kod pro github.com/login/device.
    echo.
    gh auth login -p https -h github.com -w
    if errorlevel 1 (
        echo [CHYBA] Prihlaseni na GitHub se nezdarilo. Spust instalator znovu.
        pause
        exit /b 1
    )
)
gh auth setup-git

:: Nastaveni jmena pro automaticke commity prubehu
git config --global user.name "adafore-minipc" >nul 2>&1
git config --global user.email "adafore@users.noreply.github.com" >nul 2>&1

:: --- 5. Klonovani / aktualizace repozitare ---
echo.
echo [5/6] Stahuji stahovac z GitHubu do %INSTALL_DIR%...
if exist "%INSTALL_DIR%\.git" (
    pushd "%INSTALL_DIR%"
    git pull --rebase --autostash origin main
    popd
) else (
    if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
    git clone "%REPO_URL%" "%INSTALL_DIR%"
    if errorlevel 1 (
        echo [CHYBA] Nepodarilo se naklonovat %REPO_URL%. Zkontroluj, ze jsi prihlasen jako adafore.
        pause
        exit /b 1
    )
)

:: --- 6. Virtualni prostredi + Playwright + Chromium ---
echo.
echo [6/6] Nastavuji Python .venv a instaluji Playwright + Chromium...
pushd "%INSTALL_DIR%"
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -m venv .venv
    ) else (
        python -m venv .venv
    )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m playwright install chromium
popd

:: --- Vytvoreni zastupce na Plose ---
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"
set "LAUNCHER=%DESKTOP_DIR%\Spustit_Stahovac.bat"

> "%LAUNCHER%" (
    echo @echo off
    echo chcp 65001 ^>nul
    echo title Rodokmen Stahovac ^(adafore^)
    echo cd /d "C:\RodokmenStahovac"
    echo "C:\RodokmenStahovac\.venv\Scripts\python.exe" spustit.py
    echo pause
)

echo.
echo ============================================================
echo   HOTOVO! VSE JE NAINSTALOVANO!
echo ============================================================
echo   Slozka programu: %INSTALL_DIR%
echo   Spoustec na Plose: %LAUNCHER%
echo.
echo   Od ted staci na Plose kdykoliv spustit "Spustit_Stahovac.bat":
echo   - sam zkontroluje a stahne novou verzi i nove zadani z GitHubu
echo   - stahuje matriky bez banu a kazdych 20 min je nahrava na GitHub
echo.
set /p RUNNOW="Chces stahovac rovnou ted spustit? (A/N): "
if /i "%RUNNOW%"=="A" (
    call "%LAUNCHER%"
)
endlocal
