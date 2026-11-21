# Rodokmen Stahovač (mini PC)

Privátní samoaktualizační stahovač matričních snímků z MZA Brno (Acta Publica) pro účet `adafore`.

## Jak to funguje
1. **Instalace na mini PC (jen jednou):**
   - Zkopíruj jediný soubor `Instalovat_Rodokmen_Stahovac.bat` na mini PC a spusť ho.
   - Sám nainstaluje Git, Python, GitHub CLI (`gh`), přihlásí se k `adafore`, naklonuje tento repozitář do `C:\RodokmenStahovac`, nainstaluje Playwright + Chromium a vytvoří na Ploše **`Spustit_Stahovac.bat`**.
2. **Každé spuštění (`Spustit_Stahovac.bat` -> `spustit.py`):**
   - Automaticky zkontroluje GitHub (`adafore/rodokmen-stahovac`), zda není **nová verze `stahovac.py`** nebo **nové zadání v `knihy_k_badani.json`**, a pokud ano, rovnou je stáhne.
   - Spouští `stahovac.py` v bezpečných 20minutových blocích (šetrné tempo bez IP banu).
   - Po každém bloku (i při `Ctrl+C`) zabalí stažené PNG + `manifest.json` do ZIPu a nahraje je do privátního **GitHub Release `davky`** + odešle průběh v `knihy_k_badani.json` na GitHub.
3. **Stažení dávek na hlavním PC pro analýzu:**
   ```powershell
   $gh = "$env:USERPROFILE\.gemini\tools\gh\bin\gh.exe"
   & $gh release download davky -R adafore/rodokmen-stahovac -D .\skeny\vstup_zip
   ```
