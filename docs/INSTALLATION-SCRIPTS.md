# One-command installation and updates

## MCP server: WSL or Linux

Run inside WSL/Linux as the user who will own the service, without sudo:

```sh
curl -fsSL https://raw.githubusercontent.com/penica/escriptorium-mcp/main/install.sh | sh
```

The bootstrap downloads the latest stable release, verifies its archive and
internal checksums, installs Linux uv if it is absent, and starts the bundled
interactive installer. An interactive terminal is required even though the
script is piped. It asks for the eScriptorium URL, a hidden API key, HTTP or STDIO,
and whether to create a systemd user service. A new HTTP service starts on
`127.0.0.1:8000`; remote access requires the network settings in the
[WSL guide](../deploy/wsl/README-WSL.md). The installer does not configure Windows
startup or enable WSL systemd automatically.

For an existing HTTP user service, use:

```sh
curl -fsSL https://raw.githubusercontent.com/penica/escriptorium-mcp/main/update.sh | sh
```

The first-install command refuses an existing virtual environment and directs
you to the updater. The updater retains your configured service address, port,
credentials and archive settings. The first-install bootstrap is for WSL/Linux;
the Python MCP package itself also supports Windows and macOS.

Both commands accept an explicit version with `| sh -s -- 0.18.0` and a custom
installation directory with
`| ESCRIPTORIUM_INSTALL_DIR='/absolute/install/path' sh`.

## Skill: run on the computer where Codex runs

If Codex runs on Windows and the MCP service runs in WSL, install the skill from
Windows PowerShell. A Mac connecting to that WSL server installs the skill on the
Mac. Installing the skill does not add or change your MCP connection or credentials.

### macOS or Linux

```sh
curl -fsSL https://raw.githubusercontent.com/penica/escriptorium-mcp/main/install-skills.sh | sh
```

### Windows PowerShell

Works with Windows PowerShell 5.1 and PowerShell 7; Windows `tar` must be available:

```powershell
irm https://raw.githubusercontent.com/penica/escriptorium-mcp/main/install-skills.ps1 | iex
```

**Run the same command again to update the skill.** The scripts download the
skill, UI metadata and referenced contract guides from the latest stable release,
verify checksums, and stage everything before replacing the previous copy. The
server package in the downloaded archive is not installed on the client.

New installations use `~/.agents/skills/escriptorium` (on Windows, under your user
profile), the documented [Codex user skill location](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).
An existing legacy skill under `$CODEX_HOME/skills/escriptorium`, or
`~/.codex/skills/escriptorium` when CODEX_HOME is unset, is updated in place to
avoid creating a duplicate. If both locations contain the skill, select the
intended parent directory using `ESCRIPTORIUM_SKILLS_DIR`.

The previous copy, including local edits, is moved into a `skill-backups` folder
beside the `skills` directory, outside Codex's scanned skill directory. Local
edits are backed up, not merged. An identical installation is left unchanged.
Symlinked skill destinations are refused; specify their real parent directory
explicitly. A failed download or checksum check leaves the existing skill intact.

For a custom location on macOS/Linux:

```sh
curl -fsSL https://raw.githubusercontent.com/penica/escriptorium-mcp/main/install-skills.sh | ESCRIPTORIUM_SKILLS_DIR='/absolute/skills/path' sh
```

For a specific release on macOS/Linux, append `-s -- 0.18.0` after `sh`. In
PowerShell, optionally set the corresponding environment values before running
the command:

```powershell
$env:ESCRIPTORIUM_RELEASE_VERSION = '0.18.0'
$env:ESCRIPTORIUM_SKILLS_DIR = 'C:\Users\YOUR_USER\.agents\skills'
irm https://raw.githubusercontent.com/penica/escriptorium-mcp/main/install-skills.ps1 | iex
```

The skill becomes available on your next Codex turn. Restart Codex if it does not
appear. These scripts do not enable a skill that you explicitly disabled in Codex
configuration.
