#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "anyio>=4,<5", "mcp>=2.2,<3", "pydantic-settings>=2,<3",
#     "typer>=0.16,<1", "platformdirs>=4,<5",
# ]
# ///
# ─── How to run ───
# Install uv: https://docs.astral.sh/uv/getting-started/installation/
# From the repository root: uv run python scripts/build_release.py
# To replace this version's existing archive, append --overwrite.
# ──────────────────
"""Build the current version's documented MCP catalogue and transfer archive."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tarfile
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, ClassVar, Final

import anyio
import typer
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import PaginatedRequestParams, Tool
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

ROOT: Final = Path(__file__).resolve().parents[1]
BUNDLE_FILES: Final = (
    "README.md",
    "TOOLS.md",
    "tool-schema.json",
    "CHANGELOG.md",
    "MODULE-ROADMAP.md",
    "IMPLEMENTATION-STATUS.md",
    "ONTOLOGY-COVERAGE.md",
    "docs/MODEL-API.md",
    "docs/TRAINING-API.md",
    "docs/TRANSCRIPTION-API.md",
    "docs/SEGMENTATION-API.md",
    "docs/PAGES-API.md",
    "docs/IMPORTS-API.md",
    "docs/RELEASING.md",
    "skills/escriptorium/SKILL.md",
    "skills/escriptorium/agents/openai.yaml",
)
DEPLOY_FILES: Final = (
    "install.sh",
    "README-WSL.md",
    "config.env.example",
    "escriptorium-mcp.service",
)


class Project(BaseModel):
    """Parse the release identity while ignoring unrelated project settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    name: str = Field(pattern=r"^escriptorium-mcp$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")


class Manifest(BaseModel):
    """Parse the project section of pyproject.toml."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    project: Project


async def write_catalogue(version: str) -> int:
    """Discover public tools through STDIO without invoking any remote action."""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "escriptorium_mcp.server"],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        initialized = await session.initialize()
        if initialized.server_info.version != version:
            message = "The running MCP version does not match pyproject.toml."
            raise RuntimeError(message)
        discovered = await session.list_tools()
        tools = list(discovered.tools)
        while discovered.next_cursor:
            discovered = await session.list_tools(
                params=PaginatedRequestParams(cursor=discovered.next_cursor)
            )
            tools.extend(discovered.tools)
    schema = TypeAdapter(list[Tool]).dump_json(tools, by_alias=True, indent=2)
    _ = (ROOT / "tool-schema.json").write_bytes(schema + b"\n")
    rows = [
        "# eScriptorium MCP tools",
        "",
        f"Version {version}: {len(tools)} tools.",
        "",
        "| Tool | Description |",
        "|---|---|",
    ]
    for tool in tools:
        description = " ".join((tool.description or "").split())
        description = description.replace("|", "\\|")
        rows.append(f"| `{tool.name}` | {description} |")
    _ = (ROOT / "TOOLS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(tools)


def checksum(path: Path) -> str:
    """Hash file bytes with bounded memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_metadata(member: tarfile.TarInfo) -> tarfile.TarInfo:
    """Remove workstation ownership metadata from the public archive."""
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    return member


async def package(version: str, destination: Path) -> None:
    """Build wheels and assemble only allowlisted files in a fresh directory."""
    _ = await anyio.run_process(
        ["uv", "build"], cwd=ROOT, stdout=sys.stdout, stderr=sys.stderr
    )
    with TemporaryDirectory(prefix="release-", dir=ROOT / "dist") as temporary:
        staging = Path(temporary)
        bundle = staging / f"escriptorium-mcp-{version}-wsl"
        bundle.mkdir()
        for relative in BUNDLE_FILES:
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copy2(ROOT / relative, target)
        for name in DEPLOY_FILES:
            _ = shutil.copy2(ROOT / "deploy" / "wsl" / name, bundle / name)
        wheel = ROOT / "dist" / f"escriptorium_mcp-{version}-py3-none-any.whl"
        _ = shutil.copy2(wheel, bundle / wheel.name)
        exported = await anyio.run_process(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
            ],
            cwd=ROOT,
            stderr=sys.stderr,
        )
        _ = (bundle / "requirements.txt").write_bytes(exported.stdout)
        files = sorted(path for path in bundle.rglob("*") if path.is_file())
        sums = "".join(
            f"{checksum(path)}  {path.relative_to(bundle).as_posix()}\n"
            for path in files
        )
        _ = (bundle / "SHA256SUMS").write_text(sums, encoding="utf-8")
        archive = staging / destination.name
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(bundle, arcname=bundle.name, filter=archive_metadata)
        digest = checksum(archive)
        sidecar = staging / f"{destination.name}.sha256"
        _ = sidecar.write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
        _ = archive.replace(destination)
        _ = sidecar.replace(destination.with_name(sidecar.name))


def main(
    *,
    overwrite: Annotated[
        bool, typer.Option(help="Replace an existing archive.")
    ] = False,
) -> None:
    """Generate the catalogue, wheel, source archive and WSL transfer bundle."""
    if Path.cwd().resolve() != ROOT:
        message = "Run this command from the repository root."
        raise typer.BadParameter(message)
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = Manifest.model_validate(tomllib.load(stream)).project
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    destination = dist / f"escriptorium-mcp-{project.version}-wsl.tar.gz"
    if destination.exists() and not overwrite:
        message = "Archive already exists; use --overwrite to replace it."
        raise typer.BadParameter(message)
    count = anyio.run(write_catalogue, project.version)
    anyio.run(package, project.version, destination)
    typer.echo(f"Built {project.version}: {count} tools; {destination}")


if __name__ == "__main__":
    typer.run(main)
