#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/mac-harness ]]; then
  echo "Run Setup.command first."
  read -r "?Press Return to close. "
  exit 1
fi
exec .venv/bin/mac-harness
