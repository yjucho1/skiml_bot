#!/usr/bin/env bash
set -euo pipefail

install -d -o skimlbot -g skimlbot -m 700 /opt/skiml-bot/.ssh
install -o skimlbot -g skimlbot -m 600 /tmp/.env /opt/skiml-bot/app/.env
install -o skimlbot -g skimlbot -m 600 /tmp/google-calendar-token.json \
  /opt/skiml-bot/app/.secrets/google-calendar-token.json
install -o skimlbot -g skimlbot -m 600 /tmp/slurm-monitor \
  /opt/skiml-bot/app/.secrets/slurm-monitor
install -o skimlbot -g skimlbot -m 600 /tmp/known_hosts \
  /opt/skiml-bot/app/.secrets/known_hosts
install -o skimlbot -g skimlbot -m 600 /tmp/ssh-config /opt/skiml-bot/.ssh/config

rm -f /tmp/.env /tmp/google-calendar-token.json /tmp/slurm-monitor /tmp/known_hosts /tmp/ssh-config
