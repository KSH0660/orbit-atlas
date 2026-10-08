#!/usr/bin/env bash
# Offline installer (run on the closed-network server, from the extracted bundle directory).
#
#   sudo PREFIX=/opt/spec2kb DATA_DIR=/var/lib/spec2kb ./install_offline.sh
#
# Needs only: python3.11 (RHEL 8: dnf install python3.11) — no internet, no compiler, no Node.js.
set -euo pipefail

BUNDLE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/opt/spec2kb}"
DATA_DIR="${DATA_DIR:-/var/lib/spec2kb}"
ENV_DIR="${ENV_DIR:-/etc/spec2kb}"
PY="${PYTHON:-python3.11}"
SERVICE_USER="${SERVICE_USER:-spec2kb}"
SKIP_SYSTEM="${SKIP_SYSTEM:-0}"   # 1 = do not create the service user / systemd unit (e.g. user-level install)

command -v "$PY" >/dev/null || { echo "ERROR: $PY not found. RHEL 8: dnf install python3.11"; exit 1; }
"$PY" - <<'EOF'
import sys
if sys.version_info[:2] != (3, 11):
    sys.exit(f"ERROR: Python 3.11 required, found {sys.version.split()[0]}")
EOF

if [ -f "$BUNDLE/SHA256SUMS" ]; then
  echo "==> verifying wheel checksums"
  ( cd "$BUNDLE/wheelhouse" && sha256sum -c --quiet ../SHA256SUMS )
fi

echo "==> creating virtual environment in $PREFIX/venv"
mkdir -p "$PREFIX"
"$PY" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install --no-index --find-links "$BUNDLE/wheelhouse" -r "$BUNDLE/requirements.txt"
"$PREFIX/venv/bin/python" -m pip install --no-index --no-deps "$BUNDLE"/wheelhouse/spec2kb-*.whl
if [ -f "$BUNDLE/requirements-viewer.txt" ]; then
  "$PREFIX/venv/bin/python" -m pip install --no-index --find-links "$BUNDLE/wheelhouse" -r "$BUNDLE/requirements-viewer.txt" || \
    echo "WARN: optional MkDocs viewer not installed"
fi

echo "==> preparing data directory $DATA_DIR and config $ENV_DIR"
mkdir -p "$DATA_DIR"
if [ "$(id -u)" = 0 ] && [ "$SKIP_SYSTEM" != 1 ]; then
  id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /sbin/nologin "$SERVICE_USER"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
  mkdir -p "$ENV_DIR"
  if [ ! -f "$ENV_DIR/spec2kb.env" ]; then
    sed "s#^S2K_DATA_DIR=.*#S2K_DATA_DIR=$DATA_DIR#" "$BUNDLE/deploy/spec2kb.env.example" > "$ENV_DIR/spec2kb.env"
    chmod 640 "$ENV_DIR/spec2kb.env"
    chown root:"$SERVICE_USER" "$ENV_DIR/spec2kb.env"
  fi
  sed -e "s#/opt/spec2kb#$PREFIX#g" -e "s#/var/lib/spec2kb#$DATA_DIR#g" -e "s#/etc/spec2kb#$ENV_DIR#g" \
      -e "s#^User=.*#User=$SERVICE_USER#" -e "s#^Group=.*#Group=$SERVICE_USER#" \
      "$BUNDLE/deploy/spec2kb.service" > /etc/systemd/system/spec2kb.service
  systemctl daemon-reload || true
fi

echo "==> self-test"
S2K_DATA_DIR="$(mktemp -d)" "$PREFIX/venv/bin/spec2kb" doctor --full

cat <<EOF

Installed spec2kb into $PREFIX/venv
Next steps:
  1. Edit $ENV_DIR/spec2kb.env (port, internal model endpoint key variables, basic auth)
  2. systemctl enable --now spec2kb
  3. Open http://<server>:8765 and register the in-house model under '모델 / API'
  4. Acceptance test with the sample PDFs in $BUNDLE/samples
EOF
