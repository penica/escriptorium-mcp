#!/bin/sh
main() {
    set -eu
    umask 077
    fail() { printf '%s\n' "$*" >&2; exit 1; }
    [ "$(id -u)" != 0 ] || fail 'Run as the Linux user who installed the MCP, without sudo.'
    [ "$#" -le 1 ] || fail 'Usage: sh update.sh [0.18.0]'
    install_dir=${ESCRIPTORIUM_INSTALL_DIR:-"$HOME/.local/share/escriptorium-mcp"}
    case "$install_dir" in /*) ;; *) fail 'ESCRIPTORIUM_INSTALL_DIR must be absolute.' ;; esac
    PATH="$PATH:$HOME/.local/bin:$install_dir/bin"
    export PATH
    for command_name in curl tar bash uv systemctl; do
        command -v "$command_name" >/dev/null 2>&1 || fail "Required command missing: $command_name"
    done
    python_bin="$install_dir/.venv/bin/python"
    [ -x "$python_bin" ] && [ -f "$install_dir/config.env" ] ||
        fail 'No existing installation found. Install the WSL bundle first, or set ESCRIPTORIUM_INSTALL_DIR.'
    systemctl --user cat escriptorium-mcp >/dev/null 2>&1 ||
        fail 'No accessible escriptorium-mcp user service. Run as its owning Linux user.'
    [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/escriptorium-mcp.service" ] ||
        fail 'Expected an existing per-user service file; use the interactive installer for initial setup.'
    "$python_bin" -c 'from dotenv import dotenv_values; import sys; c=dotenv_values(sys.argv[1]); sys.exit(0 if c.get("ESCRIPTORIUM_URL") and c.get("ESCRIPTORIUM_API_KEY") and c.get("ESCRIPTORIUM_HTTP_TOKEN") else "Saved URL, API key and HTTP token are required; rerun the interactive installer first.")' "$install_dir/config.env"
    repo_url=https://github.com/penica/escriptorium-mcp
    version=${1:-}
    if [ -z "$version" ]; then
        latest_url=$(curl -fsSL --connect-timeout 20 --max-time 120 -o /dev/null -w '%{url_effective}' "$repo_url/releases/latest")
        case "$latest_url" in
            "$repo_url/releases/tag/v"*) version=${latest_url##*/v} ;;
            *) fail 'GitHub did not return a release tag.' ;;
        esac
    fi
    printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail 'Expected a stable version such as 0.18.0.'
    installed=$("$python_bin" -c 'from importlib.metadata import version; print(version("escriptorium-mcp"))')
    if [ "$installed" = "$version" ] && [ ! -f "$install_dir/.update-incomplete" ]; then
        printf 'Already on %s. Service state was left unchanged.\n' "$version"
        return
    fi
    "$python_bin" -c 'import sys; import re; valid=all(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", v) for v in sys.argv[1:]); sys.exit(0 if valid and tuple(map(int, sys.argv[1].split("."))) <= tuple(map(int, sys.argv[2].split("."))) else "Refusing a downgrade or unsupported installed version.")' "$installed" "$version"
    mkdir "$install_dir/.update-lock" 2>/dev/null || fail 'Another update may be running (.update-lock exists).'
    work_dir=
    update_started=no
    cleanup() {
        result=$?
        trap - EXIT
        [ -z "$work_dir" ] || rm -rf -- "$work_dir"
        rmdir "$install_dir/.update-lock"
        if [ "$result" -ne 0 ] && [ "$update_started" = yes ]; then
            printf '%s\n' 'Update did not finish. The service may be stopped; resolve the error above and rerun the updater. No automatic rollback was attempted.' >&2
        fi
        exit "$result"
    }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    work_dir=$(mktemp -d "${TMPDIR:-/tmp}/escriptorium-update.XXXXXX")
    cd "$work_dir"
    archive="escriptorium-mcp-$version-wsl.tar.gz"
    asset_url="$repo_url/releases/download/v$version"
    printf 'Downloading and checking %s (installed: %s)...\n' "$version" "$installed"
    curl -fsSL --connect-timeout 20 --max-time 300 "$asset_url/$archive" -o "$archive"
    curl -fsSL --connect-timeout 20 --max-time 120 "$asset_url/$archive.sha256" -o "$archive.sha256"
    # Verify just the requested archive, never paths supplied by a checksum file.
    "$python_bin" -c 'import hashlib, pathlib, sys; p=pathlib.Path(sys.argv[1]); expected=pathlib.Path(sys.argv[1]+".sha256").read_text().split(); sys.exit(0 if len(expected)==2 and expected[1]==p.name and hashlib.sha256(p.read_bytes()).hexdigest()==expected[0] else "Release checksum mismatch; service unchanged.")' "$archive"
    tar -xzf "$archive"
    bundle_dir="$work_dir/escriptorium-mcp-$version-wsl"
    [ -f "$bundle_dir/install.sh" ] || fail 'Release archive does not contain its installer.'
    cd "$bundle_dir"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum --check SHA256SUMS
    else
        shasum -a 256 --check SHA256SUMS
    fi
    printf 'Updating %s to %s; keeping configuration and the existing service...\n' "$installed" "$version"
    printf '%s\n' "$version" > "$install_dir/.update-incomplete"
    update_started=yes
    systemctl --user stop escriptorium-mcp
    # Keep URL/key, select HTTP, restart the service, retain its existing unit.
    printf '\n\n1\ny\nn\n' | bash ./install.sh "$install_dir"
    actual=$("$python_bin" -c 'from importlib.metadata import version; print(version("escriptorium-mcp"))')
    [ "$actual" = "$version" ] || fail "Installed version is $actual, expected $version."
    systemctl --user is-active --quiet escriptorium-mcp || fail 'The MCP service is not active.'
    rm "$install_dir/.update-incomplete"
    printf 'Updated to %s. Service is active. Reconnect your MCP client to refresh its tools.\n' "$version"
}

# Keep execution at the end so a truncated download cannot start the update.
main "$@"
