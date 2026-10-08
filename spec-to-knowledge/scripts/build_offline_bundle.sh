#!/usr/bin/env bash
# Build an offline installation bundle for the closed network (RHEL 8.10, Python 3.11, x86_64).
#
# Run on a machine WITH internet access (any Linux/macOS/Windows-WSL with Python 3.11 + pip):
#     scripts/build_offline_bundle.sh [OUTPUT_DIR] [--with-mkdocs]
# Result: spec2kb-offline-<version>.tar.gz (+ .sha256) containing
#     wheelhouse/          all runtime wheels for manylinux (glibc <= 2.28) + the spec2kb wheel
#     requirements*.txt    pinned versions
#     install_offline.sh   installer for the target server
#     deploy/              systemd unit, environment template, nginx example
#     samples/             sample PDFs for acceptance testing
#     README.md docs/      documentation
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3.11}"
OUT=""
WITH_MKDOCS=0
for arg in "$@"; do
  case "$arg" in
    --with-mkdocs) WITH_MKDOCS=1 ;;
    *) OUT="$arg" ;;
  esac
done
OUT="${OUT:-$ROOT/offline-bundle}"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | cut -d'"' -f2)"
NAME="spec2kb-offline-$VERSION"
STAGE="$OUT/$NAME"

command -v "$PY" >/dev/null || { echo "Python 3.11 interpreter '$PY' not found (set PYTHON=...)"; exit 1; }
echo "==> building $NAME in $OUT"
rm -rf "$STAGE"
mkdir -p "$STAGE/wheelhouse"

PLATFORM_ARGS=(--only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64
               --platform manylinux_2_28_x86_64 --python-version 3.11 --implementation cp
               --abi cp311 --abi abi3 --abi none)

echo "==> downloading runtime wheels for linux x86_64 / CPython 3.11"
"$PY" -m pip download "${PLATFORM_ARGS[@]}" -r "$ROOT/requirements.txt" -d "$STAGE/wheelhouse"
if [ "$WITH_MKDOCS" = 1 ]; then
  echo "==> downloading optional MkDocs viewer wheels"
  "$PY" -m pip download "${PLATFORM_ARGS[@]}" -r "$ROOT/requirements-viewer.txt" -d "$STAGE/wheelhouse"
  cp "$ROOT/requirements-viewer.txt" "$STAGE/"
fi

echo "==> building the spec2kb wheel"
"$PY" -m pip wheel --no-deps "$ROOT" -w "$STAGE/wheelhouse"

echo "==> copying installer, deployment files, docs and samples"
cp "$ROOT/requirements.txt" "$ROOT/README.md" "$STAGE/"
cp "$ROOT/scripts/install_offline.sh" "$STAGE/"
cp -r "$ROOT/deploy" "$STAGE/deploy"
cp -r "$ROOT/docs" "$STAGE/docs"
mkdir -p "$STAGE/samples"
cp "$ROOT"/samples/*.pdf "$STAGE/samples/"
chmod +x "$STAGE/install_offline.sh"
( cd "$STAGE/wheelhouse" && sha256sum ./*.whl > ../SHA256SUMS )

echo "==> creating archive"
( cd "$OUT" && tar czf "$NAME.tar.gz" "$NAME" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256" )
echo "Done: $OUT/$NAME.tar.gz"
echo "Wheels: $(ls "$STAGE/wheelhouse" | wc -l)  (copy the .tar.gz and .sha256 to the closed network)"
