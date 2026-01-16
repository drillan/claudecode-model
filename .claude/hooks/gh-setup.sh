#!/bin/bash
# gh-setup.sh - Install GitHub CLI (gh) for Claude Code on the Web
# Reference: https://zenn.dev/oikon/articles/claude-code-web-gh-cli

set -euo pipefail

# Only run in Claude Code on the Web (remote session)
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

# Check if gh is already installed
if command -v gh &> /dev/null; then
    exit 0
fi

# Configuration
GH_VERSION="2.66.1"
INSTALL_DIR="${HOME}/.local/bin"
TMP_DIR=$(mktemp -d)

cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

# Create install directory
mkdir -p "${INSTALL_DIR}"

# Download and extract gh
echo "Installing GitHub CLI v${GH_VERSION}..."
curl -sL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
    -o "${TMP_DIR}/gh.tar.gz"
tar -xzf "${TMP_DIR}/gh.tar.gz" -C "${TMP_DIR}"
cp "${TMP_DIR}/gh_${GH_VERSION}_linux_amd64/bin/gh" "${INSTALL_DIR}/gh"
chmod +x "${INSTALL_DIR}/gh"

# Persist PATH in CLAUDE_ENV_FILE if available
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "PATH=${INSTALL_DIR}:\${PATH}" >> "${CLAUDE_ENV_FILE}"
fi

# Update PATH for current session
export PATH="${INSTALL_DIR}:${PATH}"

echo "GitHub CLI installed successfully: $(gh --version | head -1)"
