#!/usr/bin/env bash
# Fail if a bare print( appears in core package (allow in cli.py).
set -euo pipefail
if grep -R "print(" curaflow | grep -v "cli.py" | grep -v "rprint"; then
  echo "Bare print() found (exclude cli.py or use rich logger)." >&2
  exit 1
fi
exit 0
