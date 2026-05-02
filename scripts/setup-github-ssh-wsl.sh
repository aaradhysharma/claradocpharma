#!/usr/bin/env bash
# Run inside WSL: bash scripts/setup-github-ssh-wsl.sh
set -euo pipefail

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -C "wsl-gitgithub" -f "$HOME/.ssh/id_ed25519" -N ""
fi

ssh-keyscan -t ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
chmod 600 "$HOME/.ssh/known_hosts" 2>/dev/null || true

cat > "$HOME/.ssh/config" << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
EOF
chmod 600 "$HOME/.ssh/config"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
git remote set-url origin git@github.com:aaradhysharma/claradocpharma.git

echo ""
echo "Remote is now:"
git remote -v
echo ""
echo "Add this public key at https://github.com/settings/keys -> New SSH key"
echo "Then run: git fetch origin && git push origin main"
echo ""
echo "--- PUBLIC KEY ---"
cat "$HOME/.ssh/id_ed25519.pub"
echo ""
echo "--- END ---"
