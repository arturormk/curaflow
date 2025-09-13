#!/usr/bin/env bash
set -euo pipefail
pytest -q tests/test_cli_plan.py tests/test_diffing.py
