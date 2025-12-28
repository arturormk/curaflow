#!/usr/bin/env bash
# Fail if a bare print( appears in core package (allow in cli.py).
set -euo pipefail

# Match "print(" only when it's not part of a larger identifier
# (e.g. avoid false positives like "build_debug_print(").
if grep -RE '(^|[^[:alnum:]_])print\(' curaflow \
  | grep -v "cli.py" \
  | grep -v "rprint" \
  | grep -v "debug_print.py"; then
  echo "Bare print() found (exclude cli.py or use rich logger)." >&2
  exit 1
fi
exit 0
