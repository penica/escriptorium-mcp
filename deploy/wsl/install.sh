#!/usr/bin/env bash
set -euo pipefail
umask 077
bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_dir="${1:-$HOME/.local/share/escriptorium-mcp}"
case "$install_dir" in /*) ;; *) echo 'Installation directory must be absolute.' >&2; exit 2 ;; esac
command -v uv >/dev/null || { echo 'Install Linux uv first: https://docs.astral.sh/uv/'; exit 1; }
cd "$bundle_dir"
if command -v sha256sum >/dev/null; then sha256sum --check SHA256SUMS; else shasum -a 256 --check SHA256SUMS; fi
mkdir -p "$install_dir/bin"
if [ ! -e "$install_dir/.venv" ]; then
    uv venv --python 3.11 "$install_dir/.venv"
    uv pip install --python "$install_dir/.venv/bin/python" --require-hashes -r requirements.txt
    uv pip install --python "$install_dir/.venv/bin/python" --no-deps escriptorium_mcp-0.9.0-py3-none-any.whl
else
    installed_version="$("$install_dir/.venv/bin/python" -c 'from importlib.metadata import version; print(version("escriptorium-mcp"))')"
    if [ "$installed_version" != '0.9.0' ]; then
        if command -v systemctl >/dev/null && systemctl --user is-active --quiet escriptorium-mcp 2>/dev/null; then
            echo 'Stop the service before upgrading: systemctl --user stop escriptorium-mcp'
            exit 1
        fi
        echo "Upgrading $installed_version to 0.9.0; saved configuration will be retained."
        uv pip install --python "$install_dir/.venv/bin/python" --require-hashes -r requirements.txt
        uv pip install --python "$install_dir/.venv/bin/python" --no-deps escriptorium_mcp-0.9.0-py3-none-any.whl
    else
        echo 'Existing 0.9.0 installation found; configuring it again.'
    fi
fi
python_bin="$install_dir/.venv/bin/python"
config_file="$install_dir/config.env"
read_config() {
    "$python_bin" -c 'from dotenv import dotenv_values; import sys; print(dotenv_values(sys.argv[1]).get(sys.argv[2]) or "")' "$config_file" "$1"
}
current_url="$(read_config ESCRIPTORIUM_URL)"
current_url="${current_url:-http://127.0.0.1:8091/}"
while true; do
    read -r -p "eScriptorium URL [$current_url]: " selected_url
    selected_url="${selected_url:-$current_url}"
    if selected_url="$("$python_bin" -c 'import sys; from pydantic import HttpUrl; u=HttpUrl(sys.argv[1]); assert not (u.username or u.password or u.query or u.fragment), "Use a site URL without credentials/query/fragment"; print(str(u).removesuffix("/").removesuffix("/api") + "/")' "$selected_url" 2>/dev/null)"; then break; fi
    echo 'Enter an http:// or https:// site root URL.'
done
current_key="$(read_config ESCRIPTORIUM_API_KEY)"
while true; do
    if [ -n "$current_key" ]; then prompt='API key (hidden; Enter keeps the existing key): '; else prompt='API key (hidden): '; fi
    read -r -s -p "$prompt" selected_key
    printf '\n'
    selected_key="${selected_key:-$current_key}"
    [ -n "$selected_key" ] && break
    echo 'An API key is required.'
done
while true; do
    read -r -p 'Transport: 1) Streamable HTTP  2) STDIO [1]: ' selection
    case "${selection:-1}" in 1|streamable-http) transport=streamable-http; break ;; 2|stdio) transport=stdio; break ;; *) echo 'Choose 1 or 2.' ;; esac
done
install_service=no
if [ "$transport" = streamable-http ]; then
    read -r -p 'Install and start a systemd user service? [Y/n]: ' answer
    case "$answer" in ''|y|Y|yes|YES) install_service=yes ;; esac
fi
if [ -f "$config_file" ]; then
    backup="$(mktemp "$config_file.backup.XXXXXX")"
    cp "$config_file" "$backup"
    chmod 600 "$backup"
    printf 'Previous configuration backed up to %s\n' "$backup"
else
    cp config.env.example "$config_file"
fi
ESCRIPTORIUM_INSTALL_URL="$selected_url" ESCRIPTORIUM_INSTALL_KEY="$selected_key" "$python_bin" - "$config_file" <<'PY'
import os
import secrets
import sys
from dotenv import dotenv_values, set_key
path = sys.argv[1]
set_key(path, 'ESCRIPTORIUM_URL', os.environ['ESCRIPTORIUM_INSTALL_URL'])
set_key(path, 'ESCRIPTORIUM_API_KEY', os.environ['ESCRIPTORIUM_INSTALL_KEY'])
if not dotenv_values(path).get('ESCRIPTORIUM_HTTP_TOKEN'):
    set_key(path, 'ESCRIPTORIUM_HTTP_TOKEN', secrets.token_urlsafe(32))
PY
unset selected_key current_key
chmod 600 "$config_file"
ln -sfn "$(command -v uv)" "$install_dir/bin/uv"
{
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'export ESCRIPTORIUM_ENV_FILE=%q\n' "$config_file"
    printf 'export PATH=%q:"$PATH"\n' "$install_dir/bin"
    printf 'exec %q --transport %q "$@"\n' "$install_dir/.venv/bin/escriptorium-mcp" "$transport"
} > "$install_dir/bin/escriptorium-mcp"
chmod 700 "$install_dir/bin/escriptorium-mcp"
command_dir="${ESCRIPTORIUM_INSTALL_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$command_dir"
if [ ! -e "$command_dir/escriptorium-mcp" ] && [ ! -L "$command_dir/escriptorium-mcp" ]; then
    ln -s "$install_dir/bin/escriptorium-mcp" "$command_dir/escriptorium-mcp"
elif [ "$(readlink "$command_dir/escriptorium-mcp" || true)" != "$install_dir/bin/escriptorium-mcp" ]; then
    echo 'An existing escriptorium-mcp command was left unchanged; use the full launcher path below.'
fi
printf '\nConfigured launcher: %s/bin/escriptorium-mcp\n' "$install_dir"
printf 'If the command is not found, run: export PATH=%q:"$PATH"\n' "$command_dir"
if [ "$install_service" = yes ]; then
    if ! command -v systemctl >/dev/null || ! systemctl --user show-environment >/dev/null 2>&1; then
        echo 'Configuration saved, but a systemd user session is unavailable. Follow README-WSL.md or run the launcher manually.'
        exit 1
    fi
    unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$unit_dir"
    write_unit=yes
    if [ -e "$unit_dir/escriptorium-mcp.service" ]; then
        read -r -p 'Replace the existing escriptorium-mcp user service? [y/N]: ' replace
        case "$replace" in y|Y|yes|YES) cp "$unit_dir/escriptorium-mcp.service" "$(mktemp "$unit_dir/escriptorium-mcp.service.backup.XXXXXX")" ;; *) write_unit=no; echo 'Keeping the existing service address, port and settings.' ;; esac
    fi
    if [ "$write_unit" = yes ]; then
    "$python_bin" - "$install_dir/bin/escriptorium-mcp" "$unit_dir/escriptorium-mcp.service" <<'PY'
import json
import sys
from pathlib import Path
command = json.dumps(sys.argv[1], ensure_ascii=False).replace('%', '%%').replace('$', '$$')
Path(sys.argv[2]).write_text('[Unit]\nDescription=eScriptorium MCP Streamable HTTP\n\n[Service]\nType=simple\nExecStart=' + command + ' --transport streamable-http --host 127.0.0.1 --port 8000\nRestart=on-failure\nRestartSec=5\nUMask=0077\n\n[Install]\nWantedBy=default.target\n', encoding='utf-8')
PY
    fi
    systemctl --user daemon-reload
    systemctl --user enable escriptorium-mcp
    systemctl --user restart escriptorium-mcp
    sleep 2
    if ! systemctl --user is-active --quiet escriptorium-mcp; then
        echo 'Service failed to stay active. Inspect: journalctl --user -u escriptorium-mcp -n 50'
        exit 1
    fi
    if [ "$write_unit" = yes ]; then
        echo 'Service is active: http://127.0.0.1:8000/mcp'
    else
        echo 'Service is active with your existing endpoint settings.'
    fi
else
    echo 'Run the configured launcher when ready. No service was installed or stopped.'
fi
printf 'API key and HTTP token are stored privately in %s\n' "$config_file"
echo 'Remote access and Windows/WSL startup still require the networking/lifecycle setup in README-WSL.md.'
