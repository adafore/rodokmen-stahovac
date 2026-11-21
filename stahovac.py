#!/usr/bin/env python3
"""
stahovac.py – Fáze 1: Rychlý Playwright stahovač matričních snímků podle časového limitu
a fronty knihy_k_badani.json (bez AI a bez obcházení bezpečnostních prvků).

Použití:
  py stahovac.py --minut 5
  py stahovac.py --url "<START_URL>" --stran 10
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
from playwright.sync_api import sync_playwright

BASE_DIR = pathlib.Path(__file__).resolve().parent
KNIHY_CONFIG = BASE_DIR / "knihy_k_badani.json"
CILOVA_SLOZKA = BASE_DIR / "skeny" / "vstup"
PROFIL_PROHLIZECE = BASE_DIR / "profil_prohlizece"

CEKANI_ALTCHA_S = 3.0        # počáteční pauza 3 s po otevření stránky
PAUZA_MIN_S = 6.5            # velmi šetrné tempo (~6–7 stran/min -> minimální zátěž MZA)
PAUZA_MAX_S = 9.5
PRESTAVKA_KAZDYCH = 10       # každých 10 stran krátká pauza 10–15 s
DLOUHA_PRESTAVKA_KAZDYCH = 40  # každých 40 stran delší pauza 35–45 s pro mnohahodinový běh


def _over_dostupnost_mza(timeout_s: float = 5.0) -> bool:
    """Rychle ověří, zda server www.mza.cz:443 přijímá TCP spojení."""
    try:
        with socket.create_connection(("www.mza.cz", 443), timeout=timeout_s):
            return True
    except OSError:
        return False


def _najdi_platno(page):
    """Vrátí viditelný lokátor plátna OpenSeadragon (nebo None)."""
    platno = page.locator(".openseadragon-canvas, canvas").first
    try:
        if platno.count() > 0 and platno.is_visible():
            box = platno.bounding_box()
            if box and box.get("width", 0) > 200 and box.get("height", 0) > 200:
                return platno
    except Exception:
        pass
    return None


def _zrus_fokus_platna(page) -> None:
    """Zruší aktivní fokus na plátně, aby Chromium nekreslil okrajový rámeček."""
    try:
        page.evaluate(
            "() => { if (document.activeElement && document.activeElement.blur) "
            "document.activeElement.blur(); "
            "const el = document.querySelector('.openseadragon-canvas, canvas'); "
            "if (el && el.blur) el.blur(); }"
        )
    except Exception:
        pass


def _extraktuj_jp2_prefix(html: str, url: str) -> str | None:
    """Extrahuje prefix souboru .jp2 z URL nebo stránky pro přímou navigaci na snímek."""
    for zdroj in (url, html):
        m = re.search(r"image=([0-9A-Za-z_-]+)-\d{5}\.jp2", zdroj or "")
        if m:
            return m.group(1)
    m = re.search(r"([0-9]+-[0-9]+-[0-9]+-[0-9]+-[0-9]+-[0-9]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)-\d{5}\.jp2", html or "")
    return m.group(1) if m else None


def _cekej_rychle_na_platno(page, timeout_s: float = 2.5) -> None:
    """Vyčká na přítomnost OpenSeadragon plátna a náhodnou lidskou prodlevu."""
    konec = time.monotonic() + timeout_s
    while time.monotonic() < konec:
        if _najdi_platno(page) is not None:
            break
        time.sleep(0.1)
    time.sleep(random.uniform(PAUZA_MIN_S, PAUZA_MAX_S))


def _bezpecne_goto(page, context, url: str) -> object:
    """Přejde na URL a odolá případnému přesměrování / ERR_ABORTED při startu Altchy."""
    for pokus in range(2):
        try:
            page.goto(url, wait_until="commit", timeout=45000)
            return page
        except Exception as exc:
            msg = str(exc)
            if "ERR_ABORTED" in msg or "detached" in msg.lower() or "closed" in msg.lower():
                time.sleep(1.0)
                try:
                    if page.url and page.url != "about:blank":
                        return page
                except Exception:
                    pass
                if pokus == 0:
                    page = context.new_page()
                    continue
            raise
    return page


def _otevri_prohlizec_snimku(page, context, url: str, cilovy_snimek: int) -> tuple[object, str | None]:
    """
    Otevře URL knihy/snímku. Počká 3 s na načtení a případné ověření Altchy.
    Pokud jsme na detailu knihy bez ?image=, klikne na první náhled snímku pro vstup do prohlížeče.
    """
    print(f"[i] Otevírám: {url}")
    page = _bezpecne_goto(page, context, url)
    try:
        page.bring_to_front()
    except Exception:
        pass
    print(f"[i] Čekám {CEKANI_ALTCHA_S:.0f} s na načtení a ověření Altchy...")
    time.sleep(CEKANI_ALTCHA_S)

    # Pokud jsme na stránce detailu bez ?image=, vstoupíme do prvního snímku
    if "?image=" not in (page.url or "") and _najdi_platno(page) is None:
        odkaz = page.locator("a[href*='?image=']").first
        try:
            if odkaz.count() > 0 and odkaz.is_visible():
                odkaz.click(timeout=5000)
                time.sleep(1.0)
        except Exception:
            pass

    if _najdi_platno(page) is None:
        print("[i] Plátno ještě není viditelné – pokud je na obrazovce Altcha, potvrď ji v prohlížeči...")
        while _najdi_platno(page) is None:
            time.sleep(0.4)

    jp2_prefix = _extraktuj_jp2_prefix(page.content() or "", page.url or "")
    if jp2_prefix and f"-{cilovy_snimek * 10:05d}.jp2" not in (page.url or ""):
        cil = f"{url.split('?')[0]}?image={jp2_prefix}-{cilovy_snimek * 10:05d}.jp2"
        page = _bezpecne_goto(page, context, cil)
        _cekej_rychle_na_platno(page)
    else:
        _cekej_rychle_na_platno(page, timeout_s=1.2)
    return page, jp2_prefix


def _zachyt_snimek_byty(page) -> bytes:
    """Pořídí PNG bajty plátna nebo viditelné stránky."""
    _zrus_fokus_platna(page)
    platno = _najdi_platno(page)
    if platno is not None:
        return platno.screenshot(type="png", animations="disabled")
    return page.screenshot(type="png", full_page=False, animations="disabled")


def _posun_na_dalsi_snimek(
    page,
    context,
    base_url: str,
    pristi_snimek: int,
    jp2_prefix: str | None,
    predchozi_hash: str | None = None,
) -> tuple[object, str | None]:
    """
    Šetrně přejde na další snímek v Acta Publica a ověří, že se obraz skutečně změnil:
    1) klikne na UI tlačítko 'Další',
    2) pokud se URL nebo obraz nezmění, použije přímý skok ?image=<prefix>-XXXXX.jp2.
    """
    predchozi_url = page.url
    if not jp2_prefix:
        jp2_prefix = _extraktuj_jp2_prefix(page.content() or "", predchozi_url)

    pohnuto_ui = False
    for sel in (
        "a[title*='Další']",
        "button[title*='Další']",
        "a[title*='Následující']",
        "button[title*='Následující']",
        "a[title*='Next']",
        "a:has(.fa-angle-right)",
        "button:has(.fa-angle-right)",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=3000)
                _cekej_rychle_na_platno(page)
                if page.url != predchozi_url:
                    pohnuto_ui = True
                    break
        except Exception:
            continue

    # Ověříme, že se OpenSeadragon plátno skutečně překreslilo na nový snímek
    if pohnuto_ui and predchozi_hash:
        novy_hash = hashlib.sha1(_zachyt_snimek_byty(page)).hexdigest()
        if novy_hash == predchozi_hash:
            time.sleep(2.5)
            novy_hash = hashlib.sha1(_zachyt_snimek_byty(page)).hexdigest()
            if novy_hash == predchozi_hash and jp2_prefix:
                cil = f"{base_url.split('?')[0]}?image={jp2_prefix}-{pristi_snimek * 10:05d}.jp2"
                page = _bezpecne_goto(page, context, cil)
                _cekej_rychle_na_platno(page)
        return page, _extraktuj_jp2_prefix(page.content() or "", page.url or "")

    if not pohnuto_ui and jp2_prefix:
        cil = f"{base_url.split('?')[0]}?image={jp2_prefix}-{pristi_snimek * 10:05d}.jp2"
        page = _bezpecne_goto(page, context, cil)
        _cekej_rychle_na_platno(page)
    return page, jp2_prefix


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
            "    Příčina: krátkodobý výpadek MZA nebo dočasný rate-limit firewallu MZA po rychlých dotazech.\n"
            "    Tip: vyčkej cca 5–15 minut (nebo přepni Wi-Fi / mobilní hotspot) a spusť zástupce znovu."
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
        viewport_cfg = {"width": 1600, "height": 900} if use_detail else {"width": 1200, "height": 750}
        dpr_cfg = 1.5 if use_detail else 1.0
        print(f"[i] Kniha {kniha_polozka['kniha']} – rozlišení: {'DETAIL 1600x900 (1.5x)' if use_detail else 'ÚSPORNÝ REJSTŘÍK 1200x750 (1.0x)'}")

        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profil_dir),
                    headless=False,
                    viewport=viewport_cfg,
                    device_scale_factor=dpr_cfg,
                )
            except Exception:
                print("  [i] Používám nainstalovaný Google Chrome (fallback pro 32bit Windows)…")
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profil_dir),
                    channel="chrome",
                    headless=False,
                    viewport=viewport_cfg,
                    device_scale_factor=dpr_cfg,
                )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                kniha_id = kniha_polozka["kniha"]
                base_url = kniha_polozka["url"]
                snimek = int(kniha_polozka.get("aktualni_snimek") or kniha_polozka.get("od_snimku") or 1)
                do_snimku = int(kniha_polozka.get("do_snimku") or snimek)

                print(f"\n=== Kniha {kniha_id}: {kniha_polozka.get('popis', '')} (od sn. {snimek} do {do_snimku}) ===")
                page, jp2_prefix = _otevri_prohlizec_snimku(page, context, base_url, snimek)
                posledni_hash = None
                stejne_za_sebou = 0

                while snimek <= do_snimku:
                    if deadline and time.monotonic() >= deadline:
                        print("\n[⏱] Časový limit vypršel, bezpečně ukončuji.")
                        break
                    if max_stran_celkem and stazeno_celkem >= max_stran_celkem:
                        break

                    soubor_nazev = f"k{kniha_id}_sn{snimek:03d}.png"
                    soubor_cesta = cilova_slozka / soubor_nazev
                    snimek_byty = _zachyt_snimek_byty(page)
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
                        "url": page.url,
                        "cas": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    _uloz_manifest(cilova_slozka, list(manifest_by_name.values()))
                    print(f"  [{stazeno_celkem}] {soubor_nazev} -> {page.url}")

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
                        page, jp2_prefix = _posun_na_dalsi_snimek(
                            page, context, base_url, snimek, jp2_prefix, predchozi_hash=aktualni_hash
                        )
            finally:
                context.close()

    print(f"\n[✓] Hotovo! Staženo celkem {stazeno_celkem} snímků do {cilova_slozka}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fáze 1: Rychlý stahovač snímků podle knihy_k_badani.json.")
    parser.add_argument("--minut", type=float, default=None, help="Jak dlouho má stahovač běžet (v minutách)")
    parser.add_argument("--url", default=None, help="Volitelná vlastní startovní URL místo knihy_k_badani.json")
    parser.add_argument("--stran", type=int, default=None, help="Max stran při ručním režimu --url")
    parser.add_argument("--slozka", default=str(CILOVA_SLOZKA), help="Cílová složka pro PNG")
    parser.add_argument("--profil", default=str(PROFIL_PROHLIZECE), help="Trvalý profil prohlížeče")
    parser.add_argument("--detail", action="store_true", help="Vyšší rozlišení 1600x900 (1.5x) pro konkrétní cílové matriční listy")
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
