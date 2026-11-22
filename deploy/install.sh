#!/usr/bin/env bash
# Установка сайта «Карамелька» на чистый сервер Ubuntu/Debian.
# Запуск от root:   bash install.sh            (IP определится сам)
#             или:   bash install.sh 1.2.3.4
# Уже есть свой сертификат? Тогда:
#   CERT=/путь/fullchain.pem KEY=/путь/privkey.pem bash install.sh
set -euo pipefail

REPO="${REPO:-https://github.com/dalmatinec/userbot.git}"
BRANCH="${BRANCH:-main}"
DIR=/opt/karamelka
ACME=/var/www/acme

[ "$(id -u)" = 0 ] || { echo "Запусти от root (sudo -i)"; exit 1; }

CERT_ONLY=0
if [ "${1:-}" = "--cert-only" ]; then CERT_ONLY=1; shift; fi
IP="${1:-$(curl -4fsS https://api.ipify.org || curl -4fsS https://ifconfig.me)}"
echo "==> IP сервера: $IP"

if [ "$CERT_ONLY" = 0 ]; then
echo "==> Ставлю nginx, git, python"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx git python3-venv curl >/dev/null

echo "==> Забираю сайт из GitHub"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull -q --ff-only; else git clone -q -b "$BRANCH" "$REPO" "$DIR"; fi
fi
mkdir -p "$ACME"

write_nginx() {  # $1 = cert, $2 = key (пусто — только http)
  local ssl=""
  if [ -n "${1:-}" ]; then ssl="
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;
    ssl_certificate     $1;
    ssl_certificate_key $2;
    ssl_protocols TLSv1.2 TLSv1.3;
    include /etc/nginx/snippets/karamelka-site.conf;
}"; fi

  cat > /etc/nginx/snippets/karamelka-site.conf <<EOF
root $DIR/site;
index index.html;
charset utf-8;
add_header X-Robots-Tag "noindex, nofollow" always;
location / { try_files \$uri \$uri/ =404; }
location = /config.js { add_header Cache-Control "no-cache"; }
location /music/ {
    alias $DIR/music/;
    autoindex on;
    autoindex_format json;
    add_header Cache-Control "no-cache" always;
    location ~* \.(mp3|m4a|aac|ogg|opus|wav|flac)$ { add_header Cache-Control "public, max-age=86400"; }
}
location ~ /\. { deny all; }
EOF

  local http_body="include /etc/nginx/snippets/karamelka-site.conf;"
  [ -n "${1:-}" ] && http_body='location / { return 301 https://$host$request_uri; }'

  cat > /etc/nginx/sites-available/karamelka <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    location ^~ /.well-known/acme-challenge/ { root $ACME; default_type text/plain; }
    $http_body
}
$ssl
EOF
  rm -f /etc/nginx/sites-enabled/default
  ln -sf /etc/nginx/sites-available/karamelka /etc/nginx/sites-enabled/karamelka
  nginx -t -q && systemctl reload nginx
}

LE_CERT=/etc/letsencrypt/live/karamelka/fullchain.pem
LE_KEY=/etc/letsencrypt/live/karamelka/privkey.pem
SELF_DIR=/etc/karamelka

if [ "$CERT_ONLY" = 0 ]; then
  echo "==> Настраиваю nginx (http)"
  systemctl enable -q --now nginx
  if [ -f "$LE_CERT" ]; then write_nginx "$LE_CERT" "$LE_KEY"
  elif [ -f "$SELF_DIR/cert.pem" ]; then write_nginx "$SELF_DIR/cert.pem" "$SELF_DIR/key.pem"
  else write_nginx; fi
fi

if [ -n "${CERT:-}" ] && [ -n "${KEY:-}" ]; then
  echo "==> Использую готовый сертификат: $CERT"
  write_nginx "$CERT" "$KEY"
else
  echo "==> Выпускаю бесплатный сертификат Let's Encrypt на IP $IP"
  if [ ! -x /opt/certbot/bin/certbot ]; then
    python3 -m venv /opt/certbot
    /opt/certbot/bin/pip install -q --upgrade pip
    /opt/certbot/bin/pip install -q "certbot>=5.10"
  fi
  ok=0
  for try in 1 2 3 4 5; do
    if /opt/certbot/bin/certbot certonly --webroot -w "$ACME" \
        --ip-address "$IP" --preferred-profile shortlived \
        --cert-name karamelka --agree-tos --register-unsafely-without-email \
        --non-interactive --keep-until-expiring -q \
        --deploy-hook "systemctl reload nginx"; then ok=1; break; fi
    echo "    попытка $try не удалась (сеть), пробую ещё раз через 20 с…"
    sleep 20
  done

  if [ "$ok" = 1 ]; then
    echo "==> Настоящий сертификат получен"
    write_nginx "$LE_CERT" "$LE_KEY"
  elif [ -f "$LE_CERT" ]; then
    echo "==> Продлить пока не вышло, работает прежний сертификат"
    write_nginx "$LE_CERT" "$LE_KEY"
  else
    echo "==> Let's Encrypt пока не достучался до сервера. Ставлю временный сертификат,"
    echo "    сервер сам будет пробовать получить настоящий каждые 6 часов."
    mkdir -p "$SELF_DIR"
    if [ ! -f "$SELF_DIR/cert.pem" ]; then
      openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=$IP" \
        -addext "subjectAltName=IP:$IP" -keyout "$SELF_DIR/key.pem" -out "$SELF_DIR/cert.pem" 2>/dev/null
    fi
    write_nginx "$SELF_DIR/cert.pem" "$SELF_DIR/key.pem"
  fi

  if [ "$CERT_ONLY" = 1 ]; then exit 0; fi

  # IP-сертификаты живут ~6 дней: каждые 6 часов продлеваем или пробуем получить заново
  cat > /etc/systemd/system/karamelka-cert.service <<EOF
[Unit]
Description=Сертификат Карамельки
[Service]
Type=oneshot
ExecStart=/bin/bash $DIR/deploy/install.sh --cert-only $IP
EOF
  cat > /etc/systemd/system/karamelka-cert.timer <<'EOF'
[Unit]
Description=Сертификат Карамельки каждые 6 часов
[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
RandomizedDelaySec=10min
Persistent=true
[Install]
WantedBy=timers.target
EOF
fi

echo "==> Автообновление: сайт сам подтягивает изменения из GitHub каждые 2 минуты"
cat > /etc/systemd/system/karamelka-pull.service <<EOF
[Unit]
Description=Обновление сайта Карамельки из GitHub
[Service]
Type=oneshot
ExecStart=/usr/bin/git -C $DIR pull -q --ff-only
EOF
cat > /etc/systemd/system/karamelka-pull.timer <<'EOF'
[Unit]
Description=Обновление сайта Карамельки каждые 2 минуты
[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable -q --now karamelka-pull.timer
[ -f /etc/systemd/system/karamelka-cert.timer ] && systemctl enable -q --now karamelka-cert.timer

# Открыть порты, если включён ufw
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi

echo
echo "Готово 💗  Сайт: https://$IP"
