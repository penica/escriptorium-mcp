#!/bin/sh
main() {
    set -eu
    umask 077
    fail() { printf '%s\n' "$*" >&2; exit 1; }
    [ "$(id -u)" != 0 ] || fail 'Run as your normal Linux user, without sudo.'
    [ "$(uname -s)" = Linux ] || fail 'This server installer is for WSL/Linux. Skill installers also support Windows and macOS.'
    [ "$#" -le 1 ] || fail 'Usage: sh install.sh [0.18.0]'
    install_dir=${ESCRIPTORIUM_INSTALL_DIR:-"$HOME/.local/share/escriptorium-mcp"}
    case "$install_dir" in /*) ;; *) fail 'ESCRIPTORIUM_INSTALL_DIR must be absolute.' ;; esac
    [ ! -e "$install_dir/.venv" ] || fail 'An installation already exists. Use update.sh to preserve its service settings.'
    # A piped script must read credentials from the terminal, not its source stream.
    if ! { exec 3</dev/tty; } 2>/dev/null; then
        fail 'An interactive terminal is required for URL, hidden API key and transport prompts.'
    fi
    for command_name in curl tar bash; do
        command -v "$command_name" >/dev/null 2>&1 || fail "Required command missing: $command_name"
    done
    work_dir=$(mktemp -d "${TMPDIR:-/tmp}/escriptorium-install.XXXXXX")
    trap 'rm -rf -- "$work_dir"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    cd "$work_dir"
    repo_url=https://github.com/penica/escriptorium-mcp
    version=${1:-}
    if [ -z "$version" ]; then
        latest_url=$(curl -fsSL --connect-timeout 20 --max-time 120 -o /dev/null -w '%{url_effective}' "$repo_url/releases/latest")
        case "$latest_url" in "$repo_url/releases/tag/v"*) version=${latest_url##*/v} ;; *) fail 'GitHub did not return a release tag.' ;; esac
    fi
    printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail 'Expected a stable version such as 0.18.0.'
    archive="escriptorium-mcp-$version-wsl.tar.gz"
    curl -fsSL --connect-timeout 20 --max-time 300 "$repo_url/releases/download/v$version/$archive" -o "$archive"
    curl -fsSL --connect-timeout 20 --max-time 120 "$repo_url/releases/download/v$version/$archive.sha256" -o "$archive.sha256"
    read -r checksum filename extra < "$archive.sha256"
    [ "$filename" = "$archive" ] && [ -z "$extra" ] || fail 'Unexpected release checksum file.'
    printf '%s\n' "$checksum" | grep -Eq '^[a-fA-F0-9]{64}$' || fail 'Invalid release checksum.'
    printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check -
    tar -xzf "$archive"
    cd "escriptorium-mcp-$version-wsl"
    sha256sum --check SHA256SUMS
    PATH="$PATH:$HOME/.local/bin"
    export PATH
    if ! command -v uv >/dev/null 2>&1; then
        printf '%s\n' 'Installing uv for your Linux user...'
        curl -fsSL --connect-timeout 20 --max-time 120 https://astral.sh/uv/install.sh -o "$work_dir/uv-install.sh"
        UV_NO_MODIFY_PATH=1 sh "$work_dir/uv-install.sh"
    fi
    command -v uv >/dev/null 2>&1 || fail 'uv was not found. Add its installation directory to PATH and rerun.'
    bash ./install.sh "$install_dir" <&3
}

main "$@"
