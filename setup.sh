#!/bin/bash
# Установка HR-бота: bash /opt/hr-bot/setup.sh
set -e
DIR=/opt/hr-bot
cd "$DIR"
apt-get install -y -q python3-venv >/dev/null 2>&1 || true
python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  read -rp "Токен бота от @BotFather: " BOT_TOKEN
  read -rp "France Travail — Identifiant client: " FT_ID
  read -rp "France Travail — Clé secrète: " FT_SECRET
  KEY=""
  for f in /opt/french-bot/.env /opt/nice-news/.env /opt/budget-bot/.env; do
    [ -f "$f" ] && KEY=$(grep -h '^ANTHROPIC_API_KEY=' "$f" | head -1 | cut -d= -f2-) && [ -n "$KEY" ] && break
  done
  if [ -z "$KEY" ]; then read -rp "Ключ Claude API (sk-ant-...): " KEY; else echo "Ключ Claude API взят из соседнего бота."; fi
  cat > .env <<ENV
BOT_TOKEN=$BOT_TOKEN
FT_CLIENT_ID=$FT_ID
FT_CLIENT_SECRET=$FT_SECRET
ANTHROPIC_API_KEY=$KEY
DB_PATH=$DIR/hr-bot.db
ENV
  chmod 600 .env
fi

cp hr-bot.service /etc/systemd/system/hr-bot.service
systemctl daemon-reload
systemctl enable --now hr-bot
sleep 3
systemctl --no-pager --lines=5 status hr-bot | head -12
echo
echo "Готово. Напишите боту /start — он покажет Telegram ID. Затем: bash $DIR/allow.sh ID"
