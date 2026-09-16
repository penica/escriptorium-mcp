# Publishing a module release

Release one roadmap module at a time. Additive public tools increment the minor
version; corrections without a new feature use a patch release. Record the exact
scope, compatibility limits and validation in `CHANGELOG.md` and
`IMPLEMENTATION-STATUS.md`.

## Prepare

1. Update the version in `pyproject.toml`, the MCP registry, the WSL installer and
   version-specific examples. Run `uv sync` to refresh the project lock entry.
2. Update the roadmap, changelog, README, WSL instructions and agent skill for the
   released behavior. Keep credentials and live-instance evidence out of public
   files.
3. Run the relevant tests, lint and type checks. Exercise the changed tools
   through an MCP client. Use isolated fixtures for writes; real-instance checks
   must stay within the actions authorized for that instance.

## Build

From the repository root, using the project's locked environment:

```bash
uv run python scripts/build_release.py
```

The builder starts the actual local server over STDIO, verifies its advertised
version and discovers every public tool. It updates `tool-schema.json` and
`TOOLS.md`, builds the wheel and source distribution, and produces these files
under `dist/`:

- `escriptorium_mcp-VERSION-py3-none-any.whl`
- `escriptorium_mcp-VERSION.tar.gz`
- `escriptorium-mcp-VERSION-wsl.tar.gz`
- `escriptorium-mcp-VERSION-wsl.tar.gz.sha256`

No eScriptorium credentials are required for discovery; no remote tool is called.
The transfer archive contains a new, temporary bundle assembled from an explicit
allowlist: wheel, hash-locked runtime dependencies, installer, configuration and
service templates, public documentation, tool schemas and the agent skill.
`SHA256SUMS` covers every bundled file except itself. The adjacent `.sha256` file
covers the compressed archive. Dependencies are downloaded during installation;
the bundle is not an offline installer.

An existing transfer archive is preserved unless `--overwrite` is supplied:

```bash
uv run python scripts/build_release.py --overwrite
```

This replaces only the current version's generated archive and checksum after
assembly succeeds. `uv build` also replaces its current-version wheel/source
outputs. Other versions and unrelated `dist/` files are preserved. The builder
does not deploy a service, commit changes or publish to GitHub.

## Verify and publish

Inspect the archive contents and verify both the outer checksum and extracted
`SHA256SUMS`. Check the installer against a disposable installation directory,
including upgrade preservation where applicable. Inspect the wheel/source
archive for private files before distributing them. Actual WSL service/network
deployment requires a Windows/WSL environment and is separate from package QA.

Include the generated catalogue and schema in the release commit. The commit
description should state the module, new behavior, compatibility constraints,
test results and any deployment limitations. Push the commit to GitHub and
confirm the platform compatibility workflow succeeds before treating the release
as verified. Upload versioned artifacts only through the project's authorized
publication process.
