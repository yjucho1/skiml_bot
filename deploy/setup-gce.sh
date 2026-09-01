#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends ca-certificates git openssh-client python3-venv

if ! id skimlbot >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /opt/skiml-bot --shell /usr/sbin/nologin skimlbot
fi

install -d -o skimlbot -g skimlbot -m 750 /opt/skiml-bot

if [[ ! -d /opt/skiml-bot/app/.git ]]; then
  runuser -u skimlbot -- git clone --branch master https://github.com/yjucho1/skiml_bot.git \
    /opt/skiml-bot/app
else
  runuser -u skimlbot -- git -C /opt/skiml-bot/app pull --ff-only origin master
fi

install -d -o skimlbot -g skimlbot -m 700 /opt/skiml-bot/app/.secrets

python3 -m venv /opt/skiml-bot/venv
/opt/skiml-bot/venv/bin/pip install --no-cache-dir --upgrade pip
/opt/skiml-bot/venv/bin/pip install --no-cache-dir /opt/skiml-bot/app

install -o root -g root -m 644 /tmp/skiml-bot.service /etc/systemd/system/skiml-bot.service
systemctl daemon-reload
systemctl enable skiml-bot.service
