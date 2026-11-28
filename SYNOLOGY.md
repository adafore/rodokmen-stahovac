# Nasazení Rodokmen Stahovače na Synology NAS (Container Manager / Docker)

> **Důležité:** Než spustíš kontejner na Synology, **zastav stahovač na mini PC**, ať neběží dva stroje najednou ze stejné domácí IP a nepřetahují se o `knihy_k_badani.json`.

## 1. Požadavky
- Synology s **x86_64 (Intel/AMD)** procesorem (např. řada `+`) a nainstalovaným balíčkem **Container Manager** (dříve Docker).
- Alespoň **2 GB volné RAM** (6 GB je s velkou rezervou).

## 2. Vytvoření GitHub tokenu (jen jednou, ~1 minuta)
Aby kontejner mohl sám stahovat nové fronty z GitHubu a nahrávat stažené ZIPy do Release `davky`:
1. Otevři na GitHubu: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Token name:** např. `synology-rodokmen-stahovac`
3. **Expiration:** např. 1 rok (nebo Custom).
4. **Repository access:** vyber **Only select repositories** → `adafore/rodokmen-stahovac`.
5. **Permissions → Repository permissions:**
   - **Contents:** `Read and write` (stačí pro `git push` i nahrávání do GitHub Releases).
6. Klikni **Generate token** a zkopíruj vygenerovaný token (`github_pat_...`).

## 3. Nasazení v Synology Container Manageru
1. Ve **File Station** vytvoř složku např. `/docker/rodokmen-stahovac`.
2. Zkopíruj do ní tyto 4 soubory z repozitáře (nebo ji naklonuj přes SSH):
   - `Dockerfile`
   - `docker-compose.yml`
   - `docker-entrypoint.sh`
   - `requirements.txt`
3. Vytvoř v téže složce soubor `.env` (podle `.env.example`) s obsahem:
   ```env
   GH_TOKEN=github_pat_TVUJ_TOKEN
   ```
4. Otevři **Container Manager → Projekt (Project) → Vytvořit (Create)**:
   - **Název projektu:** `rodokmen-stahovac`
   - **Cesta:** `/docker/rodokmen-stahovac`
   - Zvol **Použít existující `docker-compose.yml`** → Další → Dokončit.
5. Při prvním spuštění se cca 2–4 minuty sestaví obraz (Python + Chromium + `gh` CLI + noVNC) a pak se stahovač automaticky spustí v režimu `--auto`.

## 4. Sledování běhu
- **Logy:** přímo v *Container Manager → Kontejner → rodokmen-stahovac → Protokol (Log)*.
- **Náhled prohlížeče (noVNC):** otevři v prohlížeči `http://<IP-tveho-Synology>:6080/vnc.html` a klikni **Connect** (uvidíš živé okno Chromia, příp. můžeš kdykoli ručně kliknout, kdyby bylo potřeba).
  - Pokud náhled nechceš, nastav v `docker-compose.yml` `ENABLE_NOVNC: "0"` a smaž sekci `ports:`.
- **Samoaktualizace:** stejně jako na mini PC si kontejner každé 3 minuty (při nečinnosti) nebo každých 20 minut (mezi bloky) sám stahuje nové fronty i aktualizace kódu z GitHubu.
