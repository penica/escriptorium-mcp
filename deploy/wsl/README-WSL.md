# eScriptorium MCP 0.18.0: WSL transfer bundle

Transfer `escriptorium-mcp-0.18.0-wsl.tar.gz` to the Windows computer, then extract it **inside WSL's Linux home directory**. The bundle includes the wheel, locked dependency hashes, installer, private configuration template, optional user service, full documentation and the agent skill. Internet access is needed for uv, Python and dependencies; this is not an offline installer. No API key is included.

## Upgrade directly from GitHub

Run as the Linux user who owns the existing installation, without sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/penica/escriptorium-mcp/main/update.sh | sh
```

This updates an existing WSL/Linux HTTP user service to the latest stable GitHub
release. It verifies the archive and bundled files before stopping the service,
keeps the saved URL, API key, HTTP token and archive settings, and retains the
existing service unit and overrides (including bind address and port). The
installer backs up configuration and restarts the service. No prompts are needed.
An already-current installation is left unchanged; reconnect MCP clients after
an upgrade to refresh their tool list.

For a specific release, append `-s -- 0.18.0` after `sh`. Downgrades are refused.
For a nondefault installation directory, use
`curl -fsSL https://raw.githubusercontent.com/penica/escriptorium-mcp/main/update.sh | ESCRIPTORIUM_INSTALL_DIR='/absolute/install/path' sh`.
The updater requires an existing per-user service and saved credentials; use the
interactive installer for a first installation or a STDIO setup.

If installation fails after stopping the service, the updater reports failure
and keeps a recovery marker. Resolve the reported error and rerun the command;
it can finish an interrupted update even if the package version already changed.
There is no automatic package rollback. A concurrent update is refused while
`.update-lock` exists in the installation directory. After a machine crash, remove
that empty lock directory only once you have confirmed no updater is running.

### Manual download alternative

```bash
mkdir -p ~/mcp-updates/0.18.0
cd ~/mcp-updates/0.18.0
curl -fL -O https://github.com/penica/escriptorium-mcp/releases/download/v0.18.0/escriptorium-mcp-0.18.0-wsl.tar.gz
curl -fL -O https://github.com/penica/escriptorium-mcp/releases/download/v0.18.0/escriptorium-mcp-0.18.0-wsl.tar.gz.sha256
sha256sum --check escriptorium-mcp-0.18.0-wsl.tar.gz.sha256 && tar -xzf escriptorium-mcp-0.18.0-wsl.tar.gz
```

After successful verification/extraction, stop the existing service and upgrade:

```bash
cd ~/mcp-updates/0.18.0/escriptorium-mcp-0.18.0-wsl
systemctl --user stop escriptorium-mcp && bash install.sh
```

Keep the existing URL/key, select HTTP and service installation, and answer **No** to replacing the existing service. The installer preserves its endpoint settings and restarts it. Check:

```bash
~/.local/share/escriptorium-mcp/.venv/bin/python -c 'from importlib.metadata import version; print(version("escriptorium-mcp"))'
systemctl --user status escriptorium-mcp --no-pager
journalctl --user -u escriptorium-mcp -n 50 --no-pager
```

The published 0.18.0 archive has stale 0.13.0 references in its README-WSL.md; its installer and wheel are 0.18.0. Use the versioned commands above. Reconnect MCP clients after the upgrade to refresh the 175-tool catalogue.

## 1. Extract in WSL

Adjust the Windows username/path below:

```bash
cd ~
tar -xzf /mnt/c/Users/YOUR_WINDOWS_USER/Downloads/escriptorium-mcp-0.18.0-wsl.tar.gz
cd escriptorium-mcp-0.18.0-wsl
```

Install **Linux uv inside WSL** using the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
bash install.sh
```

The installer asks for:

1. The eScriptorium site URL.
2. Your API key (hidden while typing; Enter keeps an existing key).
3. Streamable HTTP or STDIO.
4. For HTTP, whether to install and start a systemd user service.

It verifies bundled files and installs locked dependencies with Python 3.11. Running it again upgrades an older installation or reconfigures version 0.18.0, backs up its configuration, and preserves the HTTP token and archive settings. It asks before replacing an existing service. Credentials are stored with owner-only permissions and are not printed.

The configured command is linked into `~/.local/bin/escriptorium-mcp`. Open a fresh terminal, or run `export PATH="$HOME/.local/bin:$PATH"` if the command is not found. `escriptorium-mcp` starts your chosen transport automatically. If you installed the service, it is already running; do not start a second HTTP process on the same port.

If upgrading, first stop the old HTTP process (Ctrl+C) or service:

```bash
systemctl --user stop escriptorium-mcp
```

Then extract this bundle into `~/escriptorium-mcp-0.18.0-wsl` and run `bash install.sh` using the same Linux user. Keep the default installation directory. Press Enter to keep your URL/key. Choose HTTP and service installation. When asked whether to replace the existing service, press Enter (No) to retain your bind address, port and allowed hosts; the installer restarts that existing unit. Your configuration, HTTP token and NAS settings are retained. If you explicitly replace the unit, its previous version is backed up and the new unit starts on loopback. Do not delete the old configuration or virtual environment.

Set `ESCRIPTORIUM_API_KEY` and verify `ESCRIPTORIUM_URL`. The default URL is `http://127.0.0.1:8091/`, suitable when eScriptorium is published on the same WSL host. Use the actual reachable address and published port, without `/api/`. A Docker service name is not automatically reachable from the WSL host.

Only for register acquisition, configure `ESCRIPTORIUM_BOOKS_ROOT` to an existing NAS mount visible inside WSL. There is no fallback to local disk. All tool file paths refer to WSL, including when the client is on a Mac or Windows.

## 2. Start manually and check (when no service was selected)

```bash
export ESCRIPTORIUM_ENV_FILE="$HOME/.local/share/escriptorium-mcp/config.env"
export PATH="$HOME/.local/share/escriptorium-mcp/bin:$PATH"
~/.local/share/escriptorium-mcp/.venv/bin/escriptorium-mcp --transport streamable-http
```

This starts `http://127.0.0.1:8000/mcp`. In another terminal, `curl -i -X POST http://127.0.0.1:8000/mcp` should return **401 Unauthorized**: that confirms the service is running and requires authentication. Configure an HTTP MCP client with this endpoint and `Authorization: Bearer <ESCRIPTORIUM_HTTP_TOKEN from config.env>`. The service token is separate from the eScriptorium API key. Ask the client to list projects for an authenticated read-only check.

## 3. Service management / manual fallback

The interactive installer normally installs and starts the user service for you when selected. If the user systemd session is unavailable, it saves the configuration, explains the problem and exits without claiming the service is running. After enabling systemd, rerun the installer.

Alternatively, stop the foreground server first and install the supplied default-path template manually:

```bash
mkdir -p ~/.config/systemd/user
cp -i escriptorium-mcp.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now escriptorium-mcp
systemctl --user status escriptorium-mcp
journalctl --user -u escriptorium-mcp -n 50
```

The template uses the default installation directory. If you passed a custom absolute directory to `install.sh`, adjust the template before installing it. Do not copy this user unit into `/etc/systemd/system`.

If systemd is unavailable, use foreground mode or follow [Microsoft's systemd setup](https://learn.microsoft.com/en-us/windows/wsl/systemd). Enabling this service does not itself launch WSL at Windows boot or guarantee that WSL stays running. Windows startup/lifecycle configuration is separate; sleeping or shutting down the Windows host makes the MCP unavailable.

## 4. Connect from Windows or a Mac

Windows clients can generally reach a WSL listener through localhost. Remote Mac access requires Windows/WSL networking and firewall configuration; WSL's private IP may change. Follow [Microsoft's current WSL networking guide](https://learn.microsoft.com/en-us/windows/wsl/networking).

The shipped service intentionally binds to loopback. For remote access, use an HTTPS reverse proxy or authenticated SSH tunnel. For direct network binding behind an HTTPS proxy, replace the service's ExecStart arguments with `--transport streamable-http --host 0.0.0.0 --port 8000 --allowed-host YOUR_CLIENT_FACING_HOST`, then reload/restart the unit. The allowed host must match the endpoint hostname and port clients send (for example `mcp.example.internal:8000`, or the HTTPS proxy's public hostname). Preserve Host and Authorization through the proxy. Do not publish a plaintext bearer-token endpoint on the internet. See `README.md` for full transport details and private single-account limitations.

## STDIO alternative

For a local client launching the MCP within WSL, use the same environment configuration but omit `--transport streamable-http`. The executable then uses STDIO. Windows-native clients can invoke it through `wsl.exe`; choose the distribution and Linux user that own this installation.

## Agent skill and verification

Copy `skills/escriptorium` to the client agent's skill directory if needed; the skill belongs on the agent's machine, not necessarily on WSL. It does not install the MCP connection.

Version 0.18.0 exposes 175 tools, including font catalogue and transcription-font settings, native account/group operations and additive sharing, textual witnesses and alignment, virtual collections and cross-document training, expanded project/document metadata and tags, expanded native exports and generated-download management, mode-aware PDF/XML/IIIF/METS imports and optional import-group tracking, page lookup/filtering, rotation/cropping, image replacement and bulk page moves, bulk segmentation, merging, mask regeneration, reading order, supported region locking, bulk transcription edits, layer statistics and character lookup, optional training-submission tracking, raw training reports, model management/downloads, job monitoring and ontology operations. Training groups remain unproven candidates; model idle state is not successful completion. Model writes require ownership, and overwrite/replacement/deletion requires stopped training. Document associations are read-only in the audited REST API. See `docs/EXPORTS-API.md`, `docs/IMPORTS-API.md`, `docs/PAGES-API.md`, `docs/SEGMENTATION-API.md`, `docs/TRAINING-API.md` and `docs/MODEL-API.md` for API limits, `IMPLEMENTATION-STATUS.md` for release validation and `ONTOLOGY-COVERAGE.md` for ontology endpoint coverage. Actual WSL/systemd/network deployment remains to be verified on your Windows computer. Nothing is deployed automatically by transferring or extracting the archive.

Bulk transcription update is non-atomic; inspect affected records after errors.
Bulk clear retains rows/history and blanks content only. Layer deletion archives
rather than deleting its text. See `docs/TRANSCRIPTION-API.md` for scope checks,
character-count semantics and development API availability.
