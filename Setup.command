#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")"
PYTHON_BIN=""
for candidate in "$(command -v python3 2>/dev/null || true)" /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.11+ is required. Install Python, then run Setup.command again."
  read -r "?Press Return to close. "
  exit 1
fi
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
echo
echo "Setup complete. Run 'Run GUI.command' for the desktop app or Run.command for the terminal."
read -r "?Press Return to close. "
