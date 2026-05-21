#!/bin/zsh

set -euo pipefail

# Bootstrap a repo-root venv for the public pipeline subprojects.
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN="python3.13"
  else
    PYTHON_BIN="python3"
  fi
fi

"$PYTHON_BIN" -m venv --clear "$VENV_DIR"
. "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"
# Required by the implementation review queue scorer.
python -m spacy download en_core_web_sm

echo "Environment ready: $VENV_DIR"
