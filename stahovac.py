#!/usr/bin/env python3
"""
stahovac.py (v2.0.0) – Čistě Pythonový CDP stahovač matričních snímků z MZA Brno.
Používá přímo nainstalovaný Google Chrome / Edge přes Chrome DevTools Protocol (cdp_browser.py),
takže funguje bez problémů na 32bitových i 64bitových Windows bez Playwright/Node.js driveru.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import re
import socket
import time

from cdp_browser import CDPBrowser

BASE_DIR = pathlib.Path(__file__).resolve().parent
KNIHY_CONFIG = BASE_DIR / "knihy_k_badani.json"
CILOVA_SLOZKA = BASE_DIR / "skeny" / "vstup"
PROFIL_PROHLIZECE = BASE_DIR / "profil_prohlizece"

CEKANI_ALTCHA_S = 3.0
PAUZA_MIN_S = 6.5
PAUZA_MAX_S = 9.5
PRESTAVKA_KAZDYCH = 10
DLOUHA_PRESTAVKA_KAZDYCH = 40


def _over_dostupnost_mza(timeout_s: float = 5.0) -> bool:
    try:
        with socket.create_connection(("www.mza.cz", 443), timeout=timeout_s):
            return True
    except OSError:
        return False


def _extrahuj_jp2_prefix(url: str) -> str | None:
    m = re.search(r"image=([^-]+(?:-[^-]+)*)-\d{5}\.jp2", url)
    return m.group(1) if m else None


def _sestav_url_snimku(base_url: str, jp2_prefix: str | None, cislo_snimku: int) -> str:
    cista = base_url.split("?")[0]
    if jp2_prefix:
        return f"{cista}?image={jp2_prefix}-{cislo_snimku * 10:05d}.jp2"
    return base_url


def _cekej_na_platno(br: CDPBrowser, max_s: float = 20.0) -> bool:
    konec = time.monotonic() + max_s
    while time.monotonic() < konec:
        if br.canvas_box():
            return True
        time.sleep(0.5)
    return False


def _otevri_prohlizec_snimku(br: CDPBrowser, base_url: str, snimek: int) -> str | None:
    jp2_prefix = _extrahuj_jp2_prefix(base_url)
    start_url = _sestav_url_snimku(base_url, jp2_prefix, snimek) if jp2_prefix else base_url
    br.goto(start_url, wait_s=CEKANI_ALTCHA_S)

    if not _cekej_na_platno(br, max_s=6.0):
        if br.click_prohlizet():
            time.sleep(CEKANI_ALTCHA_S)
        _cekej_na_platno(br, max_s=15.0)

    if not jp2_prefix:
        jp2_prefix = _extrahuj_jp2_prefix(br.url)
        if jp2_prefix and snimek > 1:
            cil = _sestav_url_snimku(base_url, jp2_prefix, snimek)
            if cil != br.url:
                br.goto(cil, wait_s=CEKANI_ALTCHA_S)
                _cekej_na_platno(br, max_s=12.0)

    time.sleep(random.uniform(2.0, 3.0))
    return jp2_prefix


def _posun_na_dalsi_snimek(
    br: CDPBrowser,
    base_url: str,
    dalsi_snimek: int,
    jp2_prefix: str | None,
    predchozi_hash: str | None,
) -> str | None:
    pauza = random.uniform(PAUZA_MIN_S, PAUZA_MAX_S)
    time.sleep(pauza)

    pred_url = br.url
    kliknuto = br.click_dalsi()
    if kliknuto:
        time.sleep(random.uniform(2.5, 3.5))
        if br.url != pred_url:
            novy_pref = _extrahuj_jp2_prefix(br.url)
            return novy_pref or jp2_prefix
        if predchozi_hash:
            try:
                h = hashlib.sha1(br.screenshot_canvas()).hexdigest()
                if h != predchozi_hash:
                    return jp2_prefix
            except Exception:
                pass

    if not jp2_prefix:
        jp2_prefix = _extrahuj_jp2_prefix(br.url)
    if jp2_prefix:
        cil = _sestav_url_snimku(base_url, jp2_prefix, dalsi_snimek)
        br.goto(cil, wait_s=CEKANI_ALTCHA_S)
        _cekej_na_platno(br, max_s=12.0)
        time.sleep(random.uniform(1.5, 2.5))
    return jp2_prefix


def _nacti_manifest(slozka: pathlib.Path) -> list[dict]:
    cesta = slozka / "manifest.json"
    if cesta.exists():
        try:
            return json.loads(cesta.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _uloz_manifest(slozka: pathlib.Path, manifest: list[dict]) -> None:
    (slozka / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def spusti_stahovani(
    minut: float | None,
    url: str | None,
    stran: int | None,
    cilova_slozka: pathlib.Path,
    profil_dir: pathlib.Path,
    detail: bool = False,
) -> None:
    cilova_slozka.mkdir(parents=True, exist_ok=True)
    profil_dir.mkdir(parents=True, exist_ok=True)

    print("[i] Ověřuji dostupnost serveru www.mza.cz:443...")
    if not _over_dostupnost_mza(timeout_s=5.0):
        print(
            "\n[!] Server www.mza.cz (194.228.117.162:443) momentálně neodpovídá na TCP spojení.\n"
            "    Vyčkej 5–15 minut a zkus to znovu."
        )
        return

    manifest = _nacti_manifest(cilova_slozka)
    manifest_by_name = {m["soubor"]: m for m in manifest if m.get("soubor")}

    if url:
        ukoly = [
            {
                "id": "vlastni",
                "kniha": "vlastni",
                "popis": url,
                "url": url,
                "od_snimku": 1,
                "do_snimku": stran or 15,
                "aktualni_snimek": 1,
                "hotovo": False,
            }
        ]
        config_data = None
    else:
        config_data = json.loads(KNIHY_CONFIG.read_text(encoding="utf-8"))
        ukoly = [k for k in config_data.get("knihy", []) if not k.get("hotovo")]
        if not ukoly:
            print("[✓] Všechny knihy v knihy_k_badani.json jsou již označené jako hotovo.")
            return

    deadline = (time.monotonic() + minut * 60.0) if minut else None
    max_stran_celkem = stran if (url and stran) else None
    stazeno_celkem = 0

    for kniha_polozka in ukoly:
        if deadline and time.monotonic() >= deadline:
            break

        use_detail = detail or bool(kniha_polozka.get("detail", False))
        w, h = (1600, 900) if use_detail else (1200, 750)
        dpr = 1.5 if use_detail else 1.0
        print(
            f"[i] Kniha {kniha_polozka['kniha']} – rozlišení: "
            f"{'DETAIL 1600x900 (1.5x)' if use_detail else 'ÚSPORNÝ REJSTŘÍK 1200x750 (1.0x)'} [Chrome CDP]"
        )

        with CDPBrowser(profil_dir=profil_dir, width=w, height=h, dpr=dpr) as br:
            kniha_id = kniha_polozka["kniha"]
            base_url = kniha_polozka["url"]
            snimek = int(kniha_polozka.get("aktualni_snimek") or kniha_polozka.get("od_snimku") or 1)
            do_snimku = int(kniha_polozka.get("do_snimku") or snimek)

            print(f"\n=== Kniha {kniha_id}: {kniha_polozka.get('popis', '')} (od sn. {snimek} do {do_snimku}) ===")
            jp2_prefix = _otevri_prohlizec_snimku(br, base_url, snimek)
            posledni_hash: str | None = None
            stejne_za_sebou = 0

            while snimek <= do_snimku:
                if deadline and time.monotonic() >= deadline:
                    print("[⏱] Časový limit vypršel – ukládám průběh.")
                    break
                if max_stran_celkem is not None and stazeno_celkem >= max_stran_celkem:
                    break

                soubor_nazev = f"k{kniha_id}_sn{snimek:03d}.png"
                soubor_cesta = cilova_slozka / soubor_nazev

                snimek_byty = br.screenshot_canvas()
                aktualni_hash = hashlib.sha1(snimek_byty).hexdigest()
                if posledni_hash and aktualni_hash == posledni_hash:
                    stejne_za_sebou += 1
                    if stejne_za_sebou >= 2:
                        print(f"  [i] Konec knihy {kniha_id} (opakující se snímek u sn. {snimek}), přecházím na další knihu.")
                        kniha_polozka["hotovo"] = True
                        if config_data is not None:
                            KNIHY_CONFIG.write_text(
                                json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
                            )
                        break
                else:
                    stejne_za_sebou = 0
                posledni_hash = aktualni_hash

                soubor_cesta.write_bytes(snimek_byty)
                stazeno_celkem += 1
                manifest_by_name[soubor_nazev] = {
                    "soubor": soubor_nazev,
                    "cesta": f"skeny/vstup/{soubor_nazev}",
                    "kniha": kniha_id,
                    "snimek": snimek,
                    "url": br.url,
                    "cas": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                _uloz_manifest(cilova_slozka, list(manifest_by_name.values()))
                print(f"  [{stazeno_celkem}] {soubor_nazev} -> {br.url}")

                snimek += 1
                kniha_polozka["aktualni_snimek"] = snimek
                if snimek > do_snimku:
                    kniha_polozka["hotovo"] = True

                if config_data is not None:
                    KNIHY_CONFIG.write_text(
                        json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )

                if snimek <= do_snimku and (not deadline or time.monotonic() < deadline):
                    if stazeno_celkem % DLOUHA_PRESTAVKA_KAZDYCH == 0:
                        pauza_dlouha = random.uniform(35.0, 45.0)
                        print(f"  [🛑] Delší ochranná přestávka {pauza_dlouha:.1f} s po {stazeno_celkem} stranách…")
                        time.sleep(pauza_dlouha)
                    elif stazeno_celkem % PRESTAVKA_KAZDYCH == 0:
                        pauza_navic = random.uniform(10.0, 15.0)
                        print(f"  [☕] Ochranná pauza {pauza_navic:.1f} s po {stazeno_celkem} stranách…")
                        time.sleep(pauza_navic)
                    jp2_prefix = _posun_na_dalsi_snimek(
                        br, base_url, snimek, jp2_prefix, predchozi_hash=aktualni_hash
                    )

    print(f"\n[✓] Hotovo! Staženo celkem {stazeno_celkem} snímků do {cilova_slozka}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stahovač matričních snímků MZA (Chrome CDP).")
    parser.add_argument("--minut", type=float, default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--stran", type=int, default=None)
    parser.add_argument("--slozka", default=str(CILOVA_SLOZKA))
    parser.add_argument("--profil", default=str(PROFIL_PROHLIZECE))
    parser.add_argument("--detail", action="store_true")
    args = parser.parse_args()

    if args.minut is None and args.url is None:
        args.minut = 5.0

    spusti_stahovani(
        minut=args.minut,
        url=args.url,
        stran=args.stran,
        cilova_slozka=pathlib.Path(args.slozka),
        profil_dir=pathlib.Path(args.profil),
        detail=args.detail,
    )


if __name__ == "__main__":
    main()
