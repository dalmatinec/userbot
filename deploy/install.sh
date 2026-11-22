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

IP="${1:-$(curl -4fsS https://api.ipify.org || curl -4fsS https://ifconfig.me)}"
echo "==> IP сервера: $IP"

echo "==> Ставлю nginx, git, python"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx git python3-venv curl >/dev/null

echo "==> Забираю сайт из GitHub"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull -q --ff-only; else git clone -q -b "$BRANCH" "$REPO" "$DIR"; fi
mkdir -p "$ACME"

write_nginx() {  # $1 = cert, $2 = key (пусто — только http)
  local ssl=""
  if [ -n "${1:-}" ]; then ssl="
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    http2 on;
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
    location /.well-known/acme-challenge/ { root $ACME; }
    $http_body
}
$ssl
EOF
  rm -f /etc/nginx/sites-enabled/default
  ln -sf /etc/nginx/sites-available/karamelka /etc/nginx/sites-enabled/karamelka
  nginx -t -q && systemctl reload nginx
}

echo "==> Настраиваю nginx (http)"
systemctl enable -q --now nginx
write_nginx

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
  /opt/certbot/bin/certbot certonly --webroot -w "$ACME" \
    --ip-address "$IP" --preferred-profile shortlived \
    --cert-name karamelka --agree-tos --register-unsafely-without-email \
    --non-interactive --keep-until-expiring \
    --deploy-hook "systemctl reload nginx"
  write_nginx /etc/letsencrypt/live/karamelka/fullchain.pem /etc/letsencrypt/live/karamelka/privkey.pem

  # IP-сертификаты живут ~6 дней — продлеваем автоматически каждые 12 часов
  cat > /etc/systemd/system/karamelka-cert.service <<'EOF'
[Unit]
Description=Продление сертификата Карамельки
[Service]
Type=oneshot
ExecStart=/opt/certbot/bin/certbot renew -q
EOF
  cat > /etc/systemd/system/karamelka-cert.timer <<'EOF'
[Unit]
Description=Продление сертификата Карамельки каждые 12 часов
[Timer]
OnBootSec=5min
OnUnitActiveSec=12h
RandomizedDelaySec=30min
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
