#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/adafore/rodokmen-stahovac.git}"
REPO_DIR="/data/repo"

if [ -z "${GH_TOKEN:-}" ]; then
  echo "[!] Chybi promenna prostredi GH_TOKEN (GitHub Personal Access Token)."
  echo "    Nastav ji v .env nebo v docker-compose.yml a spust kontejner znovu."
  exit 1
fi

export GITHUB_TOKEN="${GH_TOKEN}"

# Virtuální displej Xvfb (Chromium poběží jako plnohodnotný desktopový prohlížeč)
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1280x800x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
sleep 1

if [ "${ENABLE_NOVNC:-1}" = "1" ]; then
  fluxbox >/tmp/fluxbox.log 2>&1 &
  x11vnc -display :99 -rfbport 5900 -forever -shared -nopw -localhost >/tmp/x11vnc.log 2>&1 &
  websockify --web=/usr/share/novnc/ 6080 localhost:5900 >/tmp/novnc.log 2>&1 &
  echo "[🖥] noVNC běží na portu 6080 (http://<IP-Synology>:6080/vnc.html)"
fi

# Nastavení Gitu a GitHub CLI
git config --global --add safe.directory "${REPO_DIR}"
git config --global user.name "${GIT_USER_NAME:-Synology Stahovac}"
git config --global user.email "${GIT_USER_EMAIL:-stahovac@synology.local}"
gh auth setup-git

mkdir -p /data
if [ ! -d "${REPO_DIR}/.git" ]; then
  echo "[↓] Klonuji repozitář ${REPO_URL} do ${REPO_DIR}…"
  git clone "${REPO_URL}" "${REPO_DIR}"
fi

cd "${REPO_DIR}"
exec python "${REPO_DIR}/spustit.py" --auto
