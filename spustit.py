#!/usr/bin/env python3
"""
spustit.py – Samoakutalizační spouštěč stahovače matrik pro mini PC.

Co dělá při každém spuštění (i průběžně mezi bloky):
1. Zkontroluje GitHub (adafore/rodokmen-stahovac), zda není nová verze stahovac.py,
   spustit.py nebo nové zadání knihy_k_badani.json, a pokud ano, automaticky ji stáhne.
2. Spouští stahovac.py po 20minutových blocích (šetří RAM a průběžně zálohuje).
3. Po každém bloku (i při přerušení Ctrl+C) zabalí nově stažené PNG + manifest.json
   do ZIPu a nahraje je do privátního GitHub Release `davky` (aby si je agent mohl
   hned stáhnout a analyzovat) a odešle průběh v knihy_k_badani.json na GitHub.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import zipfile

BASE_DIR = pathlib.Path(__file__).resolve().parent
KNIHY_JSON = BASE_DIR / "knihy_k_badani.json"
VERZE_TXT = BASE_DIR / "VERZE.txt"
REQ_TXT = BASE_DIR / "requirements.txt"
VSTUP_DIR = BASE_DIR / "skeny" / "vstup"
ODESLANO_DIR = BASE_DIR / "skeny" / "odeslano"
BALIKY_DIR = BASE_DIR / "skeny" / "baliky"
RELEASE_TAG = "davky"
BLOK_MINUT = 20.0


def _najdi_gh() -> str | None:
    """Najde spustitelný gh.exe (PATH nebo standardní instalační cesty)."""
    gh = shutil.which("gh")
    if gh:
        return gh
    kandidati = [
        pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "GitHub CLI" / "gh.exe",
        pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
        pathlib.Path.home() / ".gemini" / "tools" / "gh" / "bin" / "gh.exe",
    ]
    for k in kandidati:
        if k.exists():
            return str(k)
    return None


def _run(cmd: list[str], check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=check,
    )


def _cti_verzi() -> str:
    return VERZE_TXT.read_text(encoding="utf-8").strip() if VERZE_TXT.exists() else "?"


def _pocet_nedokoncenych() -> int:
    if not KNIHY_JSON.exists():
        return 0
    try:
        data = json.loads(KNIHY_JSON.read_text(encoding="utf-8"))
        return sum(1 for k in data.get("knihy", []) if not k.get("hotovo"))
    except Exception:
        return 0


def zkontroluj_aktualizaci() -> bool:
    """
    Stáhne případnou novou verzi stahovače nebo nové zadání z GitHubu.
    Vrací True, pokud byl aktualizován samotný spustit.py (vhodný restart).
    """
    print("\n[↻] Kontroluji novou verzi stahovače a zadání na GitHubu…")
    stary_spustit = (BASE_DIR / "spustit.py").read_bytes()
    stary_req = REQ_TXT.read_bytes() if REQ_TXT.exists() else b""
    stara_verze = _cti_verzi()

    r_fetch = _run(["git", "fetch", "origin", "main"])
    if r_fetch.returncode != 0:
        print(f"[!] Nepodařilo se spojit s GitHubem (pokračuji lokálně): {r_fetch.stderr.strip()}")
        return False

    local_sha = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = _run(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha == remote_sha:
        print(f"[✓] Máš nejnovější verzi ({stara_verze}) i aktuální zadání.")
        return False

    print("[↑] Na GitHubu je nová verze nebo nové zadání – stahuji…")
    r_pull = _run(["git", "pull", "--rebase", "--autostash", "origin", "main"])
    if r_pull.returncode != 0:
        print("[!] Konflikt při slučování – přebírám čistou verzi z GitHubu (origin/main)…")
        _run(["git", "rebase", "--abort"])
        _run(["git", "reset", "--hard", "origin/main"])

    nova_verze = _cti_verzi()
    if nova_verze != stara_verze:
        print(f"[★] Stahovač aktualizován: {stara_verze} -> {nova_verze}!")
    else:
        print("[✓] Zadání / soubory aktualizovány z GitHubu.")

    novy_req = REQ_TXT.read_bytes() if REQ_TXT.exists() else b""
    if novy_req != stary_req:
        print("[📦] Změnily se závislosti – instaluji requirements.txt…")
        _run([sys.executable, "-m", "pip", "install", "-q", "-r", str(REQ_TXT)], capture=False)

    novy_spustit = (BASE_DIR / "spustit.py").read_bytes()
    return novy_spustit != stary_spustit


def nahraj_stazene_obrazky(odeslat_stav_git: bool = True) -> int:
    """
    Zabalí všechny nové PNG + manifest.json ze skeny/vstup/ do ZIPu a nahraje
    je do privátního GitHub Release `davky`. Poté odešle stav knihy_k_badani.json.
    """
    VSTUP_DIR.mkdir(parents=True, exist_ok=True)
    ODESLANO_DIR.mkdir(parents=True, exist_ok=True)
    BALIKY_DIR.mkdir(parents=True, exist_ok=True)

    pngs = sorted(VSTUP_DIR.glob("*.png"))
    if not pngs:
        return 0

    gh = _najdi_gh()
    if not gh:
        print("[!] Nenalezen GitHub CLI (gh) – snímky zatím zůstávají lokálně v skeny/vstup/.")
        return 0

    host = socket.gethostname().replace(" ", "_")[:16]
    razitko = time.strftime("%Y%m%d_%H%M%S")
    zip_name = f"davka_{razitko}_{host}_{len(pngs)}sn.zip"
    zip_path = BALIKY_DIR / zip_name

    print(f"\n[☁] Balím {len(pngs)} stažených snímků do {zip_name}…")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in pngs:
            zf.write(p, arcname=p.name)
        manifest = VSTUP_DIR / "manifest.json"
        if manifest.exists():
            zf.write(manifest, arcname="manifest.json")

    velikost_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"    Velikost balíku: {velikost_mb:.1f} MB -> nahrávám na GitHub Release ({RELEASE_TAG})…")

    # Ujistíme se, že release `davky` existuje
    r_view = _run([gh, "release", "view", RELEASE_TAG])
    if r_view.returncode != 0:
        _run([
            gh, "release", "create", RELEASE_TAG,
            "--title", "Stažené dávky matrik (mini PC)",
            "--notes", "Automaticky nahrávané balíky matričních snímků z mini PC pro analýzu.",
        ])

    r_up = _run([gh, "release", "upload", RELEASE_TAG, str(zip_path), "--clobber"])
    if r_up.returncode != 0:
        print(f"[!] Nahrání na GitHub selhalo (soubory ponechány pro příští pokus): {r_up.stderr.strip()}")
        return 0

    print(f"[✓] Nahráno na GitHub: {zip_name} ({len(pngs)} snímků)!")

    # Přesuneme odeslané PNG do skeny/odeslano/, aby se neposílaly znovu
    for p in pngs:
        shutil.move(str(p), str(ODESLANO_DIR / p.name))
    # Smažeme lokální zip po úspěšném uploadu (šetří disk na mini PC)
    try:
        zip_path.unlink()
    except OSError:
        pass

    if odeslat_stav_git:
        r_diff = _run(["git", "status", "--porcelain", "knihy_k_badani.json"])
        if r_diff.stdout.strip():
            _run(["git", "add", "knihy_k_badani.json"])
            _run(["git", "commit", "-m", f"Průběh z {host}: +{len(pngs)} snímků ({zip_name})"])
            r_push = _run(["git", "push", "origin", "main"])
            if r_push.returncode == 0:
                print("[✓] Průběh knihy_k_badani.json odeslán na GitHub.")
            else:
                print(f"[!] Push průběhu se nezdařil (nevadí, zkusím příště): {r_push.stderr.strip()}")

    return len(pngs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Samoaktualizační spouštěč stahovače matrik.")
    parser.add_argument("--minut", type=float, default=None, help="Celkový čas běhu v minutách (0 = dokud není vše hotovo)")
    parser.add_argument("--blok", type=float, default=BLOK_MINUT, help="Délka jednoho bloku před uploadem na GitHub (výchozí 20 min)")
    parser.add_argument("--auto", action="store_true", help="Plně automatický režim (bez dotazu; po dokončení čeká a každých 10 min kontroluje GitHub)")
    parser.add_argument("--bez-aktualizace", action="store_true", help="Přeskočit kontrolu aktualizace na GitHubu")
    args = parser.parse_args()

    print("============================================================")
    print(f"  RODOKMEN STAHOVAČ (verze {_cti_verzi()}) · GitHub: adafore")
    print("============================================================")

    if not args.bez_aktualizace:
        if zkontroluj_aktualizaci():
            print("[↻] Spouštím novou verzi spustit.py…")
            os.execv(sys.executable, [sys.executable, str(BASE_DIR / "spustit.py"), *sys.argv[1:]])

    # Ujistíme se, že máme nainstalované závislosti (např. po přechodu na v2.0.0 websocket-client)
    try:
        import websocket  # noqa: F401
    except ImportError:
        print("[📦] Doinstalovávám requirements.txt (websocket-client)…")
        _run([sys.executable, "-m", "pip", "install", "-q", "-r", str(REQ_TXT)], capture=False)

    # Pokud z minulého běhu zůstaly neodeslané snímky, nejdřív je odešleme
    nahraj_stazene_obrazky(odeslat_stav_git=True)

    celkem_minut = args.minut
    if args.auto and celkem_minut is None:
        celkem_minut = 0.0
    elif celkem_minut is None:
        zbyva = _pocet_nedokoncenych()
        print(f"\nNedokončených bloků v zadání: {zbyva}")
        vstup = input("Kolik minut má stahovač běžet? [Enter = 600 (10 hodin), 0 = dokud není vše hotovo]: ").strip()
        if not vstup:
            celkem_minut = 600.0
        else:
            try:
                celkem_minut = float(vstup.replace(",", "."))
            except ValueError:
                celkem_minut = 600.0

    start = time.monotonic()
    deadline = None if celkem_minut <= 0 else (start + celkem_minut * 60.0)
    celkem_nahrano = 0
    blok_c = 0
    chyby_za_sebou = 0

    try:
        while True:
            if _pocet_nedokoncenych() == 0:
                if args.auto:
                    print("\n[💤] Všechna aktuální zadání jsou hotová. Čekám 10 minut a pak znovu zkontroluji GitHub…")
                    time.sleep(600)
                    if not args.bez_aktualizace:
                        if zkontroluj_aktualizaci():
                            os.execv(sys.executable, [sys.executable, str(BASE_DIR / "spustit.py"), *sys.argv[1:]])
                    continue
                print("\n[✓] Všechna zadání v knihy_k_badani.json jsou hotová!")
                break

            if deadline is not None:
                zbyva_min = (deadline - time.monotonic()) / 60.0
                if zbyva_min <= 0.2:
                    print("\n[⏱] Časový limit vypršel.")
                    break
                delka_bloku = min(args.blok, zbyva_min)
            else:
                delka_bloku = args.blok

            blok_c += 1
            print(f"\n--- Blok #{blok_c} ({delka_bloku:.1f} min) ---")
            res = subprocess.run(
                [sys.executable, str(BASE_DIR / "stahovac.py"), "--minut", f"{delka_bloku:.2f}"],
                cwd=str(BASE_DIR),
            )
            if res.returncode != 0:
                chyby_za_sebou += 1
                print(f"[!] stahovac.py skončil s chybou (kód {res.returncode}, pokus {chyby_za_sebou}/2).")
                if chyby_za_sebou >= 2:
                    print("[✕] Zastavuji smyčku po 2 chybách za sebou, aby se program nezacyklil.")
                    break
                time.sleep(5)
            else:
                chyby_za_sebou = 0

            celkem_nahrano += nahraj_stazene_obrazky(odeslat_stav_git=True)

            # Mezi bloky zkontrolujeme, jestli na GitHubu nepřibyla nová verze / zadání
            if not args.bez_aktualizace and (deadline is None or time.monotonic() < deadline):
                zkontroluj_aktualizaci()

    except KeyboardInterrupt:
        print("\n[!] Přerušeno uživatelem – ještě nahrávám rozdělané snímky na GitHub…")
        celkem_nahrano += nahraj_stazene_obrazky(odeslat_stav_git=True)

    print(f"\n============================================================")
    print(f"  HOTOVO! Celkem nahráno na GitHub: {celkem_nahrano} snímků.")
    print(f"============================================================")


if __name__ == "__main__":
    main()
