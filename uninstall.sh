#!/usr/bin/env bash
# Remove the Spider-Man assistant. Keeps this project folder intact.
# Pass --purge to also delete your tasks/settings in ~/.config/spiderman.
set -e

BIN="$HOME/.local/bin"
CONF="$HOME/.config/spiderman"
UNIT="$HOME/.config/systemd/user"
APPS="$HOME/.local/share/applications"

echo "🕸️  Removing Spider-Man assistant…"
systemctl --user disable --now spiderman.service 2>/dev/null || true
rm -f "$UNIT/spiderman.service"
systemctl --user daemon-reload 2>/dev/null || true
rm -f "$BIN/spiderman" "$BIN/spiderman-overlay"
rm -f "$APPS/com.stacx.LocalAsst.desktop"
echo "  ✓ service, commands and launcher removed"

if [ "$1" = "--purge" ]; then
  rm -rf "$CONF"
  echo "  ✓ purged $CONF (tasks and settings deleted)"
else
  echo "  · kept your tasks/settings in $CONF (use --purge to delete)"
fi
echo "Done. The project folder itself was not touched."
