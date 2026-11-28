#!/usr/bin/env python3
"""
cdp_browser.py – Lehký čistě Pythonový ovladač Google Chrome / Edge přes
Chrome DevTools Protocol (CDP) bez 64bitového Node.js driveru Playwrightu.
Funguje spolehlivě na 32bitových i 64bitových Windows (Python 3.9+).
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import websocket


def najdi_chrome() -> str:
    env_bin = os.environ.get("CHROME_BIN", "").strip()
    if env_bin and pathlib.Path(env_bin).exists():
        return env_bin

    if not sys.platform.startswith("win"):
        for nazev in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            nalezeno = shutil.which(nazev)
            if nalezeno:
                return nalezeno
        for cesta in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
            if pathlib.Path(cesta).exists():
                return cesta

    kandidati = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in kandidati:
        if p and pathlib.Path(p).exists():
            return p
    raise RuntimeError("Nenalezen Google Chrome, Chromium ani Microsoft Edge.")


def _volny_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CDPBrowser:
    def __init__(self, profil_dir: pathlib.Path, width: int = 1200, height: int = 750, dpr: float = 1.0):
        self.profil_dir = pathlib.Path(profil_dir)
        self.profil_dir.mkdir(parents=True, exist_ok=True)
        self.width = width
        self.height = height
        self.dpr = dpr
        self.port = _volny_port()
        self.proc: subprocess.Popen | None = None
        self.ws: websocket.WebSocket | None = None
        self._msg_id = 0

    def __enter__(self) -> "CDPBrowser":
        chrome = najdi_chrome()
        args = [
            chrome,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profil_dir}",
            f"--window-size={self.width},{self.height}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-features=TranslateUI",
        ]
        if sys.platform.startswith("linux"):
            args.extend([
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ])
        if os.environ.get("CHROME_HEADLESS", "").strip() == "1" or (
            sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
        ):
            args.append("--headless=new")
        args.append("about:blank")
        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ws_url = self._cekej_na_ws(timeout_s=20.0)
        self.ws = websocket.create_connection(ws_url, timeout=30.0)
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": self.width,
                "height": self.height,
                "deviceScaleFactor": self.dpr,
                "mobile": False,
            },
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def _cekej_na_ws(self, timeout_s: float = 20.0) -> str:
        konec = time.monotonic() + timeout_s
        url = f"http://127.0.0.1:{self.port}/json/list"
        while time.monotonic() < konec:
            try:
                with urllib.request.urlopen(url, timeout=2.0) as resp:
                    targets = json.loads(resp.read().decode("utf-8"))
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return t["webSocketDebuggerUrl"]
            except Exception:
                pass
            time.sleep(0.3)
        raise RuntimeError("Chrome nenaběhl s CDP rozhraním v časovém limitu.")

    def call(self, method: str, params: dict | None = None, timeout_s: float = 30.0) -> dict:
        assert self.ws is not None
        self._msg_id += 1
        req_id = self._msg_id
        payload = {"id": req_id, "method": method}
        if params:
            payload["params"] = params
        self.ws.settimeout(timeout_s)
        self.ws.send(json.dumps(payload))
        konec = time.monotonic() + timeout_s
        while time.monotonic() < konec:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} chyba: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(f"CDP {method} vypršel čas.")

    def eval_js(self, expr: str):
        res = self.call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": False},
        )
        return res.get("result", {}).get("value")

    @property
    def url(self) -> str:
        return str(self.eval_js("location.href") or "")

    def goto(self, target_url: str, wait_s: float = 3.0) -> None:
        self.call("Page.navigate", {"url": target_url})
        time.sleep(wait_s)

    def canvas_box(self) -> dict | None:
        js = """(() => {
            const el = document.querySelector('.openseadragon-canvas, canvas');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (r.width > 200 && r.height > 200) {
                return {x: r.left, y: r.top, width: r.width, height: r.height};
            }
            return null;
        })()"""
        return self.eval_js(js)

    def screenshot_canvas(self) -> bytes:
        self.eval_js(
            "(() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); "
            "const el = document.querySelector('.openseadragon-canvas, canvas'); if (el) el.style.outline = 'none'; })()"
        )
        box = self.canvas_box()
        params: dict = {"format": "png"}
        if box:
            params["clip"] = {
                "x": max(0, float(box["x"])),
                "y": max(0, float(box["y"])),
                "width": float(box["width"]),
                "height": float(box["height"]),
                "scale": 1.0,
            }
        res = self.call("Page.captureScreenshot", params, timeout_s=30.0)
        return base64.b64decode(res["data"])

    def click_dalsi(self) -> bool:
        js = """(() => {
            const sels = [
                'a[title*="Další"]', 'button[title*="Další"]',
                'a[aria-label*="Další"]', 'button[aria-label*="Další"]',
                'a[title*="Next"]', 'button[title*="Next"]',
                '.fa-chevron-right', '.fa-angle-right', '.fa-arrow-right',
                'a.next', 'button.next'
            ];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) {
                    const target = el.closest('a,button') || el;
                    target.click();
                    return true;
                }
            }
            return false;
        })()"""
        return bool(self.eval_js(js))

    def click_prohlizet(self) -> bool:
        js = """(() => {
            const els = Array.from(document.querySelectorAll('a, button'));
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if (/^(Prohlížet|Zobrazit)$/i.test(t)) {
                    el.click();
                    return true;
                }
            }
            return false;
        })()"""
        return bool(self.eval_js(js))
