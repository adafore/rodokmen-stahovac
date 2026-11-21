$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $extra = @(
        'C:\Program Files\Git\cmd',
        'C:\Program Files\GitHub CLI',
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
        "$env:LOCALAPPDATA\Programs\Python\Python313",
        "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts",
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts"
    ) -join ';'
    $env:Path = "$m;$u;$extra"
}

function Find-Tool($name, $fallbacks) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in $fallbacks) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Install-Winget($id, $label) {
    Write-Host "    Instaluji $label ($id)..." -ForegroundColor Yellow
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $wg) {
        throw "Na tomto PC chybi 'winget'. Nainstaluj prosim $label rucne nebo aktualizuj 'Instalator aplikaci' z Microsoft Store."
    }
    & winget install --id $id -e --source winget --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

try {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  INSTALATOR: RODOKMEN STAHOVAC PRO MINI PC (adafore)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""

    $InstallDir = 'C:\RodokmenStahovac'
    $RepoUrl    = 'https://github.com/adafore/rodokmen-stahovac.git'

    Refresh-Path

    # 1. Git
    Write-Host "[1/6] Kontroluji Git..." -ForegroundColor Green
    $gitExe = Find-Tool 'git' @('C:\Program Files\Git\cmd\git.exe', 'C:\Program Files (x86)\Git\cmd\git.exe')
    if (-not $gitExe) {
        Install-Winget 'Git.Git' 'Git'
        $gitExe = Find-Tool 'git' @('C:\Program Files\Git\cmd\git.exe', 'C:\Program Files (x86)\Git\cmd\git.exe')
    }
    if (-not $gitExe) { throw "Git se nepodarilo najit ani po instalaci. Zkus zavrit okno a spustit instalator znovu." }
    Write-Host "    OK: $gitExe"

    # 2. Python
    Write-Host "[2/6] Kontroluji Python..." -ForegroundColor Green
    $pyExe = Find-Tool 'py' @('C:\Windows\py.exe')
    if (-not $pyExe) {
        $pyExe = Find-Tool 'python' @(
            "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
            "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
            "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
        )
    }
    # Ignoruj prazdny Microsoft Store alias
    if ($pyExe -and $pyExe -like '*WindowsApps*') { $pyExe = $null }
    if (-not $pyExe) {
        Install-Winget 'Python.Python.3.12' 'Python 3.12'
        $pyExe = Find-Tool 'py' @('C:\Windows\py.exe')
        if (-not $pyExe) {
            $pyExe = Find-Tool 'python' @(
                "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
            )
        }
    }
    if (-not $pyExe) { throw "Python se nepodarilo najit ani po instalaci. Zkus instalator spustit jeste jednou." }
    Write-Host "    OK: $pyExe"

    # 3. GitHub CLI (gh)
    Write-Host "[3/6] Kontroluji GitHub CLI (gh)..." -ForegroundColor Green
    $ghExe = Find-Tool 'gh' @(
        'C:\Program Files\GitHub CLI\gh.exe',
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    )
    if (-not $ghExe) {
        Install-Winget 'GitHub.cli' 'GitHub CLI (gh)'
        $ghExe = Find-Tool 'gh' @(
            'C:\Program Files\GitHub CLI\gh.exe',
            "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
        )
    }
    if (-not $ghExe) { throw "GitHub CLI (gh) se nepodarilo najit ani po instalaci. Zkus instalator spustit jeste jednou." }
    Write-Host "    OK: $ghExe"

    # 4. Prihlaseni k GitHubu (adafore)
    Write-Host ""
    Write-Host "[4/6] Kontroluji prihlaseni na GitHub..." -ForegroundColor Green
    $ErrorActionPreference = 'Continue'
    & $ghExe auth status 2>&1 | Out-Null
    $authCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'

    if ($authCode -ne 0) {
        Write-Host ""
        Write-Host "Nyni se jednorazove prihlas ke svemu GitHub uctu (adafore)." -ForegroundColor Yellow
        Write-Host "Otevre se prohlizec (nebo se zobrazi 8mistny kod pro github.com/login/device)." -ForegroundColor Yellow
        Write-Host ""
        & $ghExe auth login -p https -h github.com -w
        if ($LASTEXITCODE -ne 0) { throw "Prihlaseni na GitHub se nezdarilo." }
    }
    & $ghExe auth setup-git
    & $gitExe config --global user.name "adafore-minipc"
    & $gitExe config --global user.email "adafore@users.noreply.github.com"

    # 5. Klonovani / aktualizace repozitare
    Write-Host ""
    Write-Host "[5/6] Stahuji stahovac z GitHubu do $InstallDir..." -ForegroundColor Green
    if (Test-Path "$InstallDir\.git") {
        Push-Location $InstallDir
        & $gitExe pull --rebase --autostash origin main
        Pop-Location
    } else {
        if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
        & $gitExe clone $RepoUrl $InstallDir
        if ($LASTEXITCODE -ne 0) { throw "Nepodarilo se naklonovat $RepoUrl." }
    }

    # 6. Virtualni prostredi + Playwright + Chromium
    Write-Host ""
    Write-Host "[6/6] Nastavuji Python .venv a instaluji Playwright + Chromium..." -ForegroundColor Green
    Push-Location $InstallDir
    $venvPy = Join-Path $InstallDir '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPy)) {
        & $pyExe -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Nepodarilo se vytvorit .venv." }
    }
    & $venvPy -m pip install --upgrade pip -q
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Instalace requirements.txt selhala." }
    & $venvPy -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Instalace Playwright Chromium selhala." }
    Pop-Location

    # Vytvoreni zastupce na Plose
    $desktop = [Environment]::GetFolderPath('Desktop')
    $launcher = Join-Path $desktop 'Spustit_Stahovac.bat'
    $launcherContent = @"
@echo off
chcp 65001 >nul
title Rodokmen Stahovac (adafore)
cd /d "C:\RodokmenStahovac"
"C:\RodokmenStahovac\.venv\Scripts\python.exe" spustit.py
pause
"@
    [System.IO.File]::WriteAllText($launcher, $launcherContent, [System.Text.UTF8Encoding]::new($false))

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  HOTOVO! VSE JE USPESNE NAINSTALOVANO!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Slozka programu:   $InstallDir"
    Write-Host "  Spoustec na Plose: $launcher"
    Write-Host ""
    $ans = Read-Host "Chces stahovac rovnou ted spustit? (A/N)"
    if ($ans -match '^[AaYy]') {
        Push-Location $InstallDir
        & $venvPy spustit.py
        Pop-Location
    }
}
catch {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "  CHYBA PRI INSTALACI:" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    exit 1
}
