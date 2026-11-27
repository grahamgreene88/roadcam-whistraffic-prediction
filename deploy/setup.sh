#!/usr/bin/env bash
# Build (or update) the logger droplet. Safe to re-run: after `git pull`, run it again.
# Run as root on a fresh Ubuntu 24.04 droplet:
#   git clone <repo-url> /opt/whistler-traffic && bash /opt/whistler-traffic/deploy/setup.sh
# This script never creates, resizes or destroys cloud resources.
set -euo pipefail

ADMIN_USER="${ADMIN_USER:-grahamg}"       # your login account (root login gets disabled)
SERVICE_USER=whistler                     # runs the loggers; cannot log in
APP_DIR=/opt/whistler-traffic
ENV_FILE=/etc/whistler-traffic/.env
UV_VERSION=0.12.7                         # same as the development laptop
export UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_CACHE_DIR=/var/cache/uv

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }
[[ -d $APP_DIR/.git ]] || { echo "Clone the repo to $APP_DIR first."; exit 1; }
log() { printf '\n==> %s\n' "$*"; }

log "Packages, tzdata, server clock in UTC"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git curl ufw unattended-upgrades
apt-get install -y -q --only-upgrade tzdata
timedatectl set-timezone UTC

log "Swap (1 GB)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "Cap system log size at 200 MB"
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=200M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald

log "Users"
id "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
if ! id "$ADMIN_USER" &>/dev/null; then
  useradd --create-home --shell /bin/bash --groups sudo "$ADMIN_USER"
  install -d -m 700 -o "$ADMIN_USER" -g "$ADMIN_USER" "/home/$ADMIN_USER/.ssh"
  install -m 600 -o "$ADMIN_USER" -g "$ADMIN_USER" /root/.ssh/authorized_keys \
    "/home/$ADMIN_USER/.ssh/authorized_keys"
  echo "Choose a password for $ADMIN_USER. It is only for sudo; SSH stays key-only."
  passwd "$ADMIN_USER"
fi

log "SSH: key login only, no root login"
if [[ -s /home/$ADMIN_USER/.ssh/authorized_keys ]]; then
  cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'EOF'
# Named 00- so it loads before cloud-init's 50- file: sshd keeps the FIRST value it reads.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
  sshd -t && (systemctl reload ssh || systemctl restart ssh)
else
  echo "WARNING: no SSH key for $ADMIN_USER; skipped SSH hardening to avoid locking you out."
fi

log "Firewall: inbound SSH only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable

log "uv $UV_VERSION and the logger's Python environment"
if [[ "$(uv --version 2>/dev/null | cut -d' ' -f2)" != "$UV_VERSION" ]]; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" \
    | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
cd "$APP_DIR"
uv sync --frozen --no-default-groups --group logger
.venv/bin/python - <<'EOF'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
off = datetime(2027, 1, 15, 12, tzinfo=ZoneInfo("America/Vancouver")).utcoffset()
assert off == timedelta(hours=-7), f"tzdata too old: Vancouver offset is {off}"
print("tzdata OK (BC permanent UTC-7)")
EOF

log "Secrets file"
install -d -m 700 "$(dirname "$ENV_FILE")"
if [[ ! -f $ENV_FILE ]]; then
  install -m 600 "$APP_DIR/.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE from the template. Fill it in (sudo nano $ENV_FILE), then re-run."
  exit 0
fi
chmod 600 "$ENV_FILE"

log "systemd units"
install -m 644 "$APP_DIR"/deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable whistler-webcams.service
systemctl restart whistler-webcams.service
systemctl --no-pager status whistler-webcams.service | head -n 5
echo "Follow the logs: journalctl -u whistler-webcams -f"
