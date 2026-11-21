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

    # 2. Python (64-bit Python 3.12 na 64bit Win; 32-bit Python 3.9 na 32bit Win kvuli binarnimu greenletu)
    $is64Win = [Environment]::Is64BitOperatingSystem
    Write-Host ("[2/6] Architektura Windows: " + $(if ($is64Win) { "64-bit" } else { "32-bit" })) -ForegroundColor Green

    function Get-PyInfo($exe) {
        if (-not $exe -or -not (Test-Path $exe)) { return $null }
        try {
            $out = & $exe -c 'import sys, struct; print(str(sys.version_info[0])+chr(46)+str(sys.version_info[1])+chr(58)+str(struct.calcsize(chr(80))*8))' 2>$null
            if ($out) { return ($out | Out-String).Trim() }
        } catch {}
        return $null
    }

    $pyExe = $null
    $targetPyVer = if ($is64Win) { '3.12' } else { '3.9' }
    $targetBits  = if ($is64Win) { '64' } else { '32' }

    if ($is64Win) {
        $kandidatiPy = @(
            "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
            "C:\Program Files\Python312\python.exe",
            "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
            "C:\Program Files\Python311\python.exe"
        )
        foreach ($kp in $kandidatiPy) {
            $info = Get-PyInfo $kp
            if ($info -eq '3.12:64' -or $info -eq '3.11:64') { $pyExe = $kp; break }
        }
        if (-not $pyExe) {
            Write-Host "    Stahuji a instaluji 64-bit Python 3.12.10 (bez C++ kompilatoru)..." -ForegroundColor Yellow
            $pyInst = "$env:TEMP\python-3.12.10-amd64.exe"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $pyInst
            $p = Start-Process -FilePath $pyInst -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_test=0' -Wait -PassThru
            Refresh-Path
            foreach ($kp in $kandidatiPy) {
                $info = Get-PyInfo $kp
                if ($info -eq '3.12:64') { $pyExe = $kp; break }
            }
        }
    } else {
        $kandidatiPy = @(
            "$env:LOCALAPPDATA\Programs\Python\Python39-32\python.exe",
            "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe",
            "C:\Program Files\Python39\python.exe",
            "C:\Python39\python.exe"
        )
        foreach ($kp in $kandidatiPy) {
            $info = Get-PyInfo $kp
            if ($info -eq '3.9:32') { $pyExe = $kp; break }
        }
        if (-not $pyExe) {
            Write-Host "    Stahuji a instaluji 32-bit Python 3.9.13 (s hotovym balickem greenlet pro 32bit Win)..." -ForegroundColor Yellow
            $pyInst = "$env:TEMP\python-3.9.13.exe"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.9.13/python-3.9.13.exe' -OutFile $pyInst
            $p = Start-Process -FilePath $pyInst -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_test=0' -Wait -PassThru
            Refresh-Path
            foreach ($kp in $kandidatiPy) {
                $info = Get-PyInfo $kp
                if ($info -eq '3.9:32') { $pyExe = $kp; break }
            }
        }
    }

    if (-not $pyExe) { throw "Nepodarilo se najit spravny Python ($targetPyVer ${targetBits}-bit) ani po instalaci." }
    $pyInfo = Get-PyInfo $pyExe
    Write-Host "    OK: $pyExe ($pyInfo)"

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
    Write-Host "[6/6] Nastavuji Python .venv ($pyInfo) a instaluji Playwright + Chromium..." -ForegroundColor Green
    Push-Location $InstallDir
    $venvPy = Join-Path $InstallDir '.venv\Scripts\python.exe'
    # Pokud existuje stare .venv z jine verze nebo bitove architektury, smazeme ho
    if (Test-Path $venvPy) {
        $vInfo = Get-PyInfo $venvPy
        if ($vInfo -ne $pyInfo) {
            Write-Host "    Odstranuji stare .venv ($vInfo) a vytvarim ciste ($pyInfo)..." -ForegroundColor Yellow
            Remove-Item -Recurse -Force (Join-Path $InstallDir '.venv')
        }
    }
    if (-not (Test-Path $venvPy)) {
        & $pyExe -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Nepodarilo se vytvorit .venv." }
    }
    & $venvPy -m pip install --upgrade pip -q
    if ($is64Win) {
        & $venvPy -m pip install --only-binary=:all: -r requirements.txt
    } else {
        & $venvPy -m pip install --only-binary=:all: "playwright==1.49.1"
    }
    if ($LASTEXITCODE -ne 0) { throw "Instalace Playwrightu selhala." }
    $ErrorActionPreference = 'Continue'
    & $venvPy -m playwright install chromium
    $pwChromeCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($pwChromeCode -ne 0) {
        $sysChrome = @('C:\Program Files\Google\Chrome\Application\chrome.exe', 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($sysChrome) {
            Write-Host "    [i] Playwright Chromium nepodporuje 32-bit – pouzije se nainstalovany Google Chrome ($sysChrome)." -ForegroundColor Yellow
        } else {
            throw "Instalace Playwright Chromium selhala a Google Chrome nebyl nalezen."
        }
    }
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

    # Automaticke spusteni ihned po zapnuti mini PC (slozka Po spusteni / Startup)
    $startupDir = [Environment]::GetFolderPath('Startup')
    $autostartBat = Join-Path $startupDir 'Rodokmen_Stahovac_AutoStart.bat'
    $autostartContent = @"
@echo off
chcp 65001 >nul
title Rodokmen Stahovac AUTO (adafore)
echo Cekam 15 sekund na pripojeni site po startu Windows...
timeout /t 15 /nobreak >nul
cd /d "C:\RodokmenStahovac"
"C:\RodokmenStahovac\.venv\Scripts\python.exe" spustit.py --auto
pause
"@
    [System.IO.File]::WriteAllText($autostartBat, $autostartContent, [System.Text.UTF8Encoding]::new($false))

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  HOTOVO! VSE JE USPESNE NAINSTALOVANO!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Slozka programu:    $InstallDir"
    Write-Host "  Spoustec na Plose:  $launcher"
    Write-Host "  Auto-start po boot: $autostartBat"
    Write-Host ""
    $ans = Read-Host "Chces stahovac rovnou ted spustit v automatickem rezimu? (A/N)"
    if ($ans -match '^[AaYy]') {
        Push-Location $InstallDir
        & $venvPy spustit.py --auto
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
