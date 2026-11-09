#!/bin/sh
# Install or refresh the Hive Mind client exactly as shipped: hive/hive.py -> ~/memory/hive.py,
# plus a ~/bin/hive wrapper. Re-run on every template upgrade (UPGRADE.md / weekly update check).
# Copies files only. Sends nothing. Does not read or write hive_state, so the on/off switch is unchanged
# (a brand-new database stays off until setup enables it; an upgrade re-run leaves the existing flag).
set -eu
PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/memory" "$HOME/bin"
cp "$PKG_DIR/hive/hive.py" "$HOME/memory/hive.py"
chmod +x "$HOME/memory/hive.py"
if [ -f "$PKG_DIR/VERSION" ]; then
  cp "$PKG_DIR/VERSION" "$HOME/memory/VERSION"
fi
printf '#!/bin/sh\nexec python3 "$HOME/memory/hive.py" "$@"\n' > "$HOME/bin/hive"
chmod +x "$HOME/bin/hive"
echo "installed $HOME/memory/hive.py and $HOME/bin/hive"
