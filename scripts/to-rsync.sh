#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="data/targets"
DEST="user@host:/var/www/dir-assets"
echo "Would rsync $SRC_DIR -> $DEST (edit this script for real deploy)."
# rsync -avz --delete "$SRC_DIR"/ "$DEST"/
