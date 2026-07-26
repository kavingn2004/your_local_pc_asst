#!/usr/bin/env bash
# Install / re-install the Spider-Man assistant from this project folder.
# Everything is user-level — no sudo required.
set -e

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
CONF="$HOME/.config/spiderman"
UNIT="$HOME/.config/systemd/user"
APPS="$HOME/.local/share/applications"

echo "🕷️  Installing Spider-Man assistant from $PROJ"
mkdir -p "$BIN" "$CONF" "$UNIT" "$APPS"

# 1. link the executables (symlinks, so edits in the project take effect)
chmod +x "$PROJ"/bin/*
ln -sf "$PROJ/bin/spiderman"         "$BIN/spiderman"
ln -sf "$PROJ/bin/spiderman-overlay" "$BIN/spiderman-overlay"
ln -sf "$PROJ/bin/spiderman"     "$BIN/local-asst"
ln -sf "$PROJ/bin/spiderman-app" "$BIN/local-asst-app"
echo "  ✓ commands linked into $BIN (spiderman + local-asst)"

# 2. assets (icon + character sprite)
cp -f "$PROJ/assets/spiderman.png"      "$CONF/" 2>/dev/null || true
cp -f "$PROJ/assets/spiderman-hero.png" "$CONF/" 2>/dev/null || true
python3 "$PROJ/tools/make_logo.py" "$CONF" >/dev/null 2>&1 && echo "  ✓ logo generated"
echo "  ✓ assets copied to $CONF"

# 3. character sprites (cut out from the bundled artwork)
if [ -d "$PROJ/assets/characters" ]; then
  python3 "$PROJ/tools/make_characters.py" "$PROJ/assets/characters" \
          "$CONF/characters" >/dev/null 2>&1 \
    && echo "  ✓ characters installed ($(ls "$CONF/characters" 2>/dev/null | wc -l) available)"
fi

# 4. systemd user service (autostart on login)
sed "s|%h|$HOME|g" "$PROJ/systemd/spiderman.service" > "$UNIT/spiderman.service"
systemctl --user daemon-reload
systemctl --user enable --now spiderman.service
echo "  ✓ service installed, enabled and started"

# 5. app-grid launcher for the GUI
sed "s|__HOME__|$HOME|g" "$PROJ/desktop/com.stacx.LocalAsst.desktop" > "$APPS/com.stacx.LocalAsst.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
echo "  ✓ app launcher installed"

echo
echo "Done. Try:  spiderman status"
echo "If 'spiderman' isn't found, open a new terminal (PATH needs $BIN)."
