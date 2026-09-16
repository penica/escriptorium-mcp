# eScriptorium MCP server

Version 0.5.0 exposes **89 tools** for eScriptorium. It uses the published [escriptorium-connector](https://pypi.org/project/escriptorium-connector/) for authentication and existing reads, plus adapters for current API actions.

## Capabilities

| Area | Available operations |
|---|---|
| Projects and documents | Browse; create; rename; move a document between project slugs; delete |
| Pages | Upload an image; import PDF/image archives; edit metadata; reorder within a document; delete |
| Transcriptions | Create/rename/delete layers; write/correct/delete line text |
| Segmentation | Create/edit/delete line baselines and polygons or regions; reorder lines; run automatic segmentation |
| Ontology and annotations | Manage types, components and taxonomies; edit image/text annotation instances; preview repairs/merges; portable schema snapshots; capability-gated native ontology files and project templates |
| OCR and models | Upload a Kraken model; list/read models; run OCR/HTR; train recognition or segmentation models |
| Jobs | List/read task reports; cancel a task, page processing or model training |
| Exports | Direct UTF-8 text/JSON export; native ALTO/PAGE XML/text export jobs; download a completed export link |
| Scan acquisition | Download an entire available register directly to NAS with a checksum manifest |

Verification results: [ontology-complete-verification.json](ontology-complete-verification.json).

See **[TOOLS.md](TOOLS.md)** for all tool names and descriptions, or **[tool-schema.json](tool-schema.json)** for exact argument schemas.

## Platforms and installation

Supports macOS, Windows and Linux with [uv](https://docs.astral.sh/uv/getting-started/installation/). The MCP process supports Python 3.11+; the legacy connector runs in its own locked Python 3.11 environment, provisioned by uv. No shell scripts, Docker or WSL are required. First use needs network access to install the worker dependencies and, if missing, Python 3.11.

Clone the repository first:

```sh
git clone https://github.com/penica/escriptorium-mcp.git
cd escriptorium-mcp
```

From this directory, the following commands work in a terminal or Windows PowerShell:

```text
uv sync --frozen
uv run escriptorium-mcp --help
uv run escriptorium-mcp
```

The last command starts STDIO and waits for MCP messages. An MCP client normally starts this process for you.

For a standalone installation, from this directory:

```text
uv tool install --python 3.11 .
```

Or install the supplied wheel using `uv tool install --python 3.11 /path/to/escriptorium_mcp-0.5.0-py3-none-any.whl`. Run `uv tool update-shell` and restart your client if the installed command is not on its PATH. The portable `mcp.json` uses that installed `escriptorium-mcp` command. If a desktop client does not inherit PATH, use the executable path reported by `uv tool dir --bin`; Windows uses `escriptorium-mcp.exe`.

## Credentials and paths

Copy `.env.example` to a private configuration file and fill in the API key. In this checkout the existing ignored `.env` remains supported regardless of working directory. For an installed package, set environment variables or point `ESCRIPTORIUM_ENV_FILE` to your configuration file. Environment variables override file values. A selected file must exist.

For example, set it in the client's server configuration (replace the path):

```json
{
  "mcpServers": {
    "escriptorium": {
      "command": "escriptorium-mcp",
      "args": [],
      "env": {"ESCRIPTORIUM_ENV_FILE": "C:/Users/you/escriptorium.env"}
    }
  }
}
```

On macOS/Linux, use a native absolute path such as `/home/you/escriptorium.env`. Forward slashes in Windows JSON paths avoid backslash escaping. In dotenv files, single-quote drive-letter or UNC paths.

- `ESCRIPTORIUM_URL`: site root, **without `/api/`**.
- `ESCRIPTORIUM_API_KEY`: eScriptorium API token; alternatively `ESCRIPTORIUM_USERNAME` and `ESCRIPTORIUM_PASSWORD`.
- `ESCRIPTORIUM_ENV_FILE`: optional explicit dotenv location.
- `ESCRIPTORIUM_BOOKS_ROOT`: existing absolute path to the mounted Books archive. Required for register acquisition, with no local fallback. macOS `/Volumes/.../Books`, Linux `/mnt/.../Books`, Windows `Z:/.../Books` or a UNC share all use the same code.
- `ESCRIPTORIUM_WORKER_DIR`: optional separate connector worker source directory.
- `ESCRIPTORIUM_WORKER_CACHE`: optional writable directory for worker environments. Defaults to the operating system's user cache. Installed package directories do not need write access.
- `ESCRIPTORIUM_HTTP_TOKEN`: separate random service token, needed only for HTTP.

The supplied key remains in the ignored checkout `.env`; package and client examples contain no credentials. Rotate it there when ready. Protect the configuration file with your operating system's file permissions.

## Transport choice (checked 16 September 2026)

**Use STDIO for a local desktop MCP client. Use Streamable HTTP when clients connect to a running service.** Both are current MCP transports. The official [remote-server guidance](https://modelcontextprotocol.io/registry/remote-servers) recommends Streamable HTTP for remote servers; the older standalone SSE transport is deprecated. This server uses MCP Python SDK 2.2 and retains the same 89 tools in either transport.

STDIO is the default and needs no listening port. To run HTTP, first generate a separate service token:

```text
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store that value as `ESCRIPTORIUM_HTTP_TOKEN` in the selected dotenv file or environment, then run:

```text
uv run escriptorium-mcp --transport streamable-http --port 8000
```

Connect your HTTP-capable MCP client to `http://127.0.0.1:8000/mcp` and send `Authorization: Bearer <service-token>`. HTTP requires a token even on loopback. Configure the header using your client's secret/environment settings, not a committed file. The eScriptorium API key is **not** the HTTP service token.

The service binds to loopback by default. For a private network deployment, bind an explicit interface and permit the exact client-facing Host header:

```text
escriptorium-mcp --transport streamable-http --host 0.0.0.0 --port 8000 --allowed-host mcp.example.internal:8000
```

Use HTTPS through a reverse proxy for network access, preserving Authorization and Host. For a proxy on port 443, permit its public Host header instead. Host checks remain enabled. Browser Origin headers are denied unless explicitly permitted with repeatable `--allowed-origin https://trusted-client.example`; non-browser MCP clients normally send no Origin.

This is a **private, single-account service** with a pre-shared bearer token, not an OAuth login service. All authorized clients use the configured eScriptorium account and the server process's filesystem access. Public/multi-user deployments need an OAuth 2.1 gateway and per-user authorization; this package does not implement those. File upload/import/export paths always refer to the **MCP server's machine**, including over HTTP. A Windows client can use a Linux-hosted HTTP server, but tool file paths must then be Linux paths.

The HTTP endpoint uses stateless requests; queued eScriptorium work remains monitored through the task tools. For large file transfers, configure client and proxy timeouts above the expected duration: ordinary actions have a 120-second worker deadline, uploads/imports/exports 30 minutes, full registers 6 hours. Reconnect clients after upgrading to refresh tool schemas.

## Agent skill

[skills/escriptorium/SKILL.md](skills/escriptorium/SKILL.md) is the portable **$escriptorium** skill. It explains tool selection, IDs, transcription corrections, processing and archive verification. Copy the `skills/escriptorium` directory into your agent's skill directory on another machine. A skill guides the agent; it does not install or connect the MCP server. This directory is also included in the source distribution.

## Ontology and annotations (0.5.0)

See [ONTOLOGY-COVERAGE.md](ONTOLOGY-COVERAGE.md) for the route-to-tool map, write semantics and server capability limits.

- `get_document_ontology` reads assigned page/region/line types and their actual IDs; `list_ontology_types` and `get_ontology_type` read public/template types. Private types may be absent from those public endpoints. Older servers share definitions globally; newer servers may copy templates to document-local IDs.
- Create, rename or delete definitions with the type tools. `add_document_ontology_type` attaches a new/reused name while retaining existing memberships. `set_document_ontology` replaces only supplied categories: omitted lists stay unchanged, `[]` clears one category. Re-read document-local IDs after attachment.
- `audit_document_ontology` scans page/region/line assignments. `replace_ontology_assignments` and `merge_ontology_types` preview by default. A null source selects untyped content; a null target clears classification. A document-local merge reassigns usage and can remove source membership without globally deleting a shared definition.
- Component and taxonomy tools manage annotation schemas. Use `patch_annotation_taxonomy` for selective edits: it reads and preserves omitted settings and relations. `update_annotation_taxonomy` deliberately replaces the full definition; supply every setting to retain it. Explicit taxonomy `components=[]` removes linked fields and `typology=null` clears its type.
- `list_annotations`, `get_annotation`, `create_image_annotation`, `update_image_annotation`, `create_text_annotation`, `update_text_annotation` and `delete_annotation` manage actual annotation instances. Image annotations use integer pixel coordinates; text annotations use segmented line IDs, a transcription layer and zero-based offsets. The returned `as_w3c` representation is read-only.
- Instance component values are **upserts**, not a replacement list: omitted components and `components=[]` preserve stored values. Set an individual component value to `null` to clear its content. The relation remains; the upstream API has no endpoint to delete only that component-value relation.
- `merge_annotation_taxonomies` previews moving all source annotations to a compatible target. The target must have the same image/text marker family and include every stored component. Source deletion requires `delete_source=true` and a clean rescan; it is otherwise retained.
- `export_ontology_snapshot` returns portable, versioned JSON **schema only**. Save the result as JSON or pass it to `restore_ontology_snapshot`. Restoration previews by default, adds missing definitions, refuses conflicting same-name definitions and never removes existing schema. It does not restore annotation instances, text, geometry or content type assignments.
- `get_ontology_capabilities` probes native document/project YAML import/export, project templates and type metadata. `export_native_ontology`, `import_native_ontology`, `get_project_ontology`, `delete_project_ontology` and `update_ontology_type_color` are available as MCP tools but require the corresponding server capability. A registered MCP tool is not a promise that an older server supports its endpoint. HTTP 403 means denied; 404 means absent or hidden, not a reliable version number.

For a document-only rename on an older server, add the replacement, use its returned document ID, preview a merge, and apply within the user's authorized scope. A global rename affects every document sharing that type. Deleting a taxonomy, component or annotation type can cascade to annotations or stored values.

**Pause other writers during repairs, taxonomy edits/merges and snapshot restoration.** These workflows span multiple API requests, without an upstream transaction or atomic conditional writes. Conflict checks reduce risk but cannot eliminate races. Inspect progress and status fields after every apply; a failure or timeout can leave partial writes, and no rollback is attempted. Re-read/audit the destination before retrying. A schema snapshot is not a full document backup for undoing destructive operations.

Native file paths belong to the MCP server host, and transfers are limited to 16 MiB. Document import may replace definitions and affect annotations; project import sets a template for future documents. Preserve the server's returned warnings. Deleting a project template leaves existing documents unchanged. On installations without native file endpoints, portable snapshots provide schema transfer through the ordinary document APIs.

## Typical workflows

### Create and populate a document

1. `list_projects` to find the project **slug**.
2. `list_scripts` to find a script **name**, such as `Latin`.
3. `create_document` with `data.name`, `data.project` (slug), and `data.main_script` (name).
4. `upload_page` with an existing image path, or `import_document_file` with a PDF, image ZIP, ALTO or PAGE XML file.
5. For imports/conversion, check `list_tasks` and page workflow before processing further.

A page is a document part. IDs are positive primary keys, not page numbers. `move_page.position.index` is a **zero-based** position within the same document. Moving an entire document to another project uses `update_document.changes.project` with the destination slug.

### Correct text and segmentation

Read `list_lines`, `list_regions`, and `get_page_transcriptions`. Use `create_line_transcription` for a new line/layer combination, or `update_line_transcription` with the existing **line transcription record ID**, which differs from the segmented line ID.

Geometry uses pixel coordinates. A baseline needs at least two points; a polygon at least three. PATCH tools only send explicitly supplied fields. Explicit `null` can clear nullable fields, such as a line's region or polygon. Empty patches are rejected.

### OCR and training

1. `list_models`, or `upload_model` with a local Kraken model (`job: 1` for segmentation, `job: 2` for recognition).
2. Create/select a transcription layer.
3. `segment_pages` and `transcribe_pages` require explicit page IDs.
4. `train_recognition` requires a ground-truth layer and either a starting model or a new model name. `train_segmentation` requires at least two distinct segmented pages and a starting model or new name.
5. Check `list_tasks`/`get_task`, `get_model` and page workflow for actual completion.

Task report states: **0 queued, 1 running, 2 crashed, 3 finished, 4 canceled**. Successful job submission is not successful processing. OCR can replace text in its target layer; segmentation/training overrides can replace existing results. Cancellation uses dedicated server actions, not a manual change to the status field.

### Export transcriptions

`export_transcriptions` directly saves one layer as text or JSON to a new local file. It covers all pages by default, or explicit `parts`, and sorts pages and lines in reading order. JSON retains IDs and available revision/confidence metadata. The result includes path, byte count and SHA-256.

For server-generated ALTO/PAGE XML/text archives, use `request_server_export`, then pass the completed link from the eScriptorium notification to `download_export`. **This installed server returns 404 for `/api/downloads/`**, so automatic discovery of server-created export links is unavailable here. Direct text/JSON export does not depend on that endpoint.

Exports never overwrite existing files and stay outside the NAS Books tree. Export downloads accept only URLs on the configured server and refuse redirects. A failed transfer leaves a `.part` file for diagnosis; choose a fresh destination after resolving it.

### Download a complete register

`download_register` requires catalogue metadata: document ID, parish, register ID, English register type and catalogue years. It downloads every available original scan to:

```text
<ESCRIPTORIUM_BOOKS_ROOT>/<parish>/<RegisterID>_<Type>_<Years>/
```

For example, `ExampleParish/02751_Baptisms_1838-1879/`. Scans are written directly to the configured archive. A new destination is required; existing folders are refused. Partial files and incremental manifests also stay on NAS. The manifest preserves original filenames, source/viewer/image URLs, byte counts and SHA-256 checksums, and distinguishes available scans from unknown historical missing pages. Acquisition does not mark visual inspection or transcription complete. Interrupted folders are retained and are not automatically resumed or overwritten.

## Implementation and verification

The connector requires Pydantic 1 and the MCP SDK uses Pydantic 2, so each runs in a separate locked environment. Each MCP call creates a worker. Page responses use a compatibility adapter because this server omits the old connector's required `bw_image` field. Additional actions use the connector's authenticated HTTP session. Error messages expose status codes and safe file errors without raw private response bodies.

```sh
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest -q
uv build
```

Tests drive real MCP STDIO processes and Streamable HTTP and the real connector against isolated HTTP fixtures. They cover mutation paths/payloads, multipart uploads/imports, task requests, input validation, bodyless deletes, pagination, direct exports, overwrite refusal, and NAS acquisition success/partial failure. Modern adapter and test code is type-checked; legacy worker code is exercised through integration tests. The repository CI matrix runs Python 3.11 and 3.13 on macOS, Windows and Linux. Local execution was on macOS; native Windows/Linux results must be confirmed by that CI.

Live checks use reads and a local transcription export only. No live records were edited/deleted and no live processing/training jobs were started. Actual OCR accuracy and training outcomes depend on installed server workers, models and training data. See `ontology-complete-verification.json` for the release verification summary.

API contracts are grounded in the live API and official [views](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/views.py), [serializers](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/serializers.py), and [import/export forms](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/imports/forms.py).
