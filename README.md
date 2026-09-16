# eScriptorium MCP server

Version 0.15.0 exposes **152 tools** for eScriptorium. It uses the published [escriptorium-connector](https://pypi.org/project/escriptorium-connector/) for authentication and existing reads, plus adapters for current API actions.

## Capabilities

| Area | Available operations |
|---|---|
| Projects and documents | Search/filter/sort; create/edit; move between project slugs; statistics/page lookup; scoped metadata and tags; delete |
| Pages | Filter/read/order lookup; upload/replace images; rotate/crop; metadata; single/bulk moves; delete |
| Transcriptions | Create/rename/delete layers; write/correct/delete line text |
| Segmentation | Read/edit lines and regions; bulk line operations and merging; masks and reading order; supported region locking |
| Ontology and annotations | Manage types, components and taxonomies; edit image/text annotation instances; preview repairs/merges; portable schema snapshots; capability-gated native ontology files and project templates |
| OCR and models | Filter/read/upload models; update owned models; replace/delete idle owned models; download weights/checkpoints; inspect document associations; run OCR/HTR and training |
| Training reports | Optionally track submission candidates; combine model metrics/checkpoints with caller-selected training reports |
| Jobs | List/read task reports; cancel a task, page processing or model training |
| Exports | Direct text/JSON; native ALTO/PAGE XML/text/JSON archives and optional formats; generated-download management |
| Scan acquisition | Download an entire available register directly to NAS with a checksum manifest |

Release validation: [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md).

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

Or install the supplied wheel using `uv tool install --python 3.11 /path/to/escriptorium_mcp-0.15.0-py3-none-any.whl`. Run `uv tool update-shell` and restart your client if the installed command is not on its PATH. The portable `mcp.json` uses that installed `escriptorium-mcp` command. If a desktop client does not inherit PATH, use the executable path reported by `uv tool dir --bin`; Windows uses `escriptorium-mcp.exe`.

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

**Use STDIO for a local desktop MCP client. Use Streamable HTTP when clients connect to a running service.** Both are current MCP transports. The official [remote-server guidance](https://modelcontextprotocol.io/registry/remote-servers) recommends Streamable HTTP for remote servers; the older standalone SSE transport is deprecated. This server uses MCP Python SDK 2.2 and retains the same 152 tools in either transport.

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

## Task and job monitoring (0.6.0)

- `list_tasks` now accepts optional `document_id`, `group_id`, `ordering`, `workflow_state` and exact `method` filters. Existing no-argument calls retain their response shape. Ordering accepts comma-separated `queued_at`, `started_at`, `done_at`, each optionally prefixed by `-`. State/method filtering happens locally after following every page because the server does not support those query filters.
- `list_document_tasks` lists document task counts and last-start timestamps, with name substring, state and staff-only user filtering. State filters select documents; the returned counts still include their historical tasks in all states.
- `list_task_groups` and `get_task_group` expose submission groups with state buckets, timestamps and associated-page counts. A group's page count does not mean completed pages.
- `get_document_job_status` summarizes the authenticated user's reports for a document, optionally restricted to a group. It preserves report messages and timestamps for diagnosis. Without a group, old jobs remain included. Groups can include other users' reports, so group counts may differ from this current-user summary.
- `get_import_status` summarizes visible import reports. It does not read native import records or invent processed/total counts. Inspect timestamps to identify the relevant import; no visible reports does not prove that no import exists.
- `cancel_document_tasks` cancels queued/running work across the document. `cancel_document_import` uses the dedicated latest-import cancellation action; it cannot choose an arbitrary historical import. Already-stopped imports return an error; affected upstream versions return HTTP 500 if no import exists.

**Completion semantics:** `terminal_percent` counts finished, crashed and canceled reports. It is not a success rate, page-completion measure or percentage inside a running job. `all_finished` is true only for a nonempty set containing exclusively Finished reports. Empty results return a null percentage; unknown states prevent success. These are paginated observations, not atomic snapshots; refresh while work is changing.

**Cancellation scope:** the existing `cancel_task` endpoint has document-wide cleanup side effects: even with one task ID, upstream also marks all document training models and imports canceled. Prefer the dedicated model or import cancellation action for those jobs. Owner/staff permissions apply. Cancellation is not transactional; re-read status after errors or timeouts before retrying.

See [CHANGELOG.md](CHANGELOG.md) for releases and [MODULE-ROADMAP.md](MODULE-ROADMAP.md) for the remaining modules.

## Virtual collections (0.15.0)

Eight tools manage owned collections and train recognition or segmentation models
from pages across documents. Each member supplies a document, page and transcription
layer. Updating `items` replaces the complete membership; `[]` clears it and omission
preserves it. `default_transcriptions` is a separate document-to-layer preference map.

Training checks every current member and selected model before one submission.
Recognition needs at least one page; segmentation needs two distinct pages.
The native response supplies a model ID, but no task/group ID. Membership is read
again when the server executes the job, so keep it stable while training is queued.
Collection writes and submissions can partially apply. See
[docs/COLLECTIONS-API.md](docs/COLLECTIONS-API.md) for ownership, model overwrite,
monitoring and upstream D-FINE limitations.

## Projects, documents and metadata (0.14.0)

Project/document lists support name, tag and ordering filters; document filtering
uses a project ID while creation/movement uses its slug. Raw reads preserve newer
fields and populated sharing/tag objects. Create/edit supports 512-character
record names, project guidelines, confidence visualization and scoped tag arrays.
Assignments replace the whole array; `[]` clears it.

Use `get_document_statistics`, `list_document_page_ids` and `find_pages_by_type`
for geometry/annotation counts and lightweight page lookup. Document/page metadata
CRUD and personal/project tag CRUD use explicit scoped targets. Ordinary metadata
updates edit a value; `update_shared_metadata_key` edits a global definition that
may affect other documents/pages. Deleting a project deletes its documents and
cascading content. See [docs/RECORDS-API.md](docs/RECORDS-API.md) for the contracts,
assignment rules, compatibility changes and limits.

## Model management (0.7.0)

- `list_models` accepts optional `document_id` and numeric `job` filters; no-argument calls retain their existing behavior. Job **1** means segmentation and **2** means recognition. Uploads and metadata writes translate these inputs to the API's required labels.
- `update_model` changes an owned model's name, job or storage-size metadata. Omit unchanged fields; nulls and empty updates are rejected. Names support 256 characters. Renaming is allowed during training, but job/size changes require an explicitly idle model. Changing a job label does not convert model weights.
- `replace_model_file` replaces an owned, idle model's weights using a file on the MCP host and updates its byte-size metadata. Replacement does not create a backup checkpoint. `delete_model` deletes an owned, idle model and its server-managed relationships; it does not delete document transcriptions. Download files first when they must be retained.
- `list_model_versions` preserves advertised revision IDs and available server-specific metrics. `download_model` saves the current file, or the checkpoint selected by `revision`, to a new local `destination` and returns its bytes and SHA-256 after completion. Paths belong to the MCP host. Existing output/partial files and the scan-only Books archive are refused. Only advertised files on the configured origin are accepted; redirects and unsafe paths are rejected. A listed file can be missing, in which case download fails without claiming completion.
- `get_model_documents` reads associated document IDs. The audited REST API has no bind/unbind operation; its `documents` field is read-only. Use the eScriptorium UI for unbinding, and do not submit processing jobs solely to create associations. Checkpoint revert/delete actions are also absent from the audited REST API.

Ownership and idle-state checks occur before writes and are not an atomic server-side lock. Pause other writers when replacing/deleting files or changing job/size metadata. See [docs/MODEL-API.md](docs/MODEL-API.md) for the supported contract and limits, and [docs/RELEASING.md](docs/RELEASING.md) for package preparation.

## Training and evaluation (0.8.0)

`train_recognition` and `train_segmentation` retain the standard server-supported fields: explicit page IDs, an existing model and/or output name, override behavior, and a recognition transcription layer. Names support 256 characters; duplicate pages and explicit null model/name options are rejected. The selected model's job must match the action. Overwriting an existing model requires ownership and stopped training, even when a new name is also supplied. The server's submission serializer validates page/layer membership; preflight model checks are not atomic locks.

Both tools accept optional `track: true`. The default preserves the raw submission response. Tracking wraps acceptance with groups observed before/after submission and marks new matching or initially unnamed-method groups as **candidates**. A single candidate is still unproven, and concurrent work can produce several. Failed monitoring does not undo an accepted submission or trigger a retry. Standard document training returns no model/group ID; acceptance is not completion.

`get_training_report` presents raw model validation scores and checkpoint metadata alongside optional caller-selected document/group task summaries. A group requires its document ID. Task/model attribution is explicitly caller-supplied, and document-only summaries include historical training reports. Idle state does not prove success, missing metrics are not zero, and an advertised checkpoint may no longer exist. Use `download_model` to verify its bytes.

The audited standard API has no independent evaluation action or request fields for epochs, learning rate, optimizer, batch size, precision, device or validation split. The MCP exposes available server metrics without converting them into invented CER/WER values. Custom ARC controls need their own API contract. See [docs/TRAINING-API.md](docs/TRAINING-API.md) for the detailed audit and attribution limits.

## Transcriptions (0.9.0)

Use `get_line_transcription` for a text record and `get_transcription` / `update_transcription` for layer settings. Page-text listing accepts an optional `transcription_id`. Line creation and updates support character graphs and average-confidence metadata; omit unchanged fields and use null only for nullable values.

`bulk_create_line_transcriptions`, `bulk_update_line_transcriptions` and `bulk_clear_line_transcriptions` use the native bulk endpoints. Before writing, the MCP checks that records, segmented lines and layers belong to the selected page/document, including paginated results. These checks are observations, not locks: pause concurrent edits. Bulk update can partially apply before returning an error; the MCP never retries it automatically. Re-read records before deciding what to submit next.

Bulk clear only blanks content. It retains rows, graphs, confidence and existing history, and creates no history revision. Individual line-transcription deletion removes a row. The existing `delete_transcription` tool archives/renames a layer and retains its text; the default manual layer is protected.

`get_transcription_statistics` returns nonempty-line count and stored-character frequencies. Sum frequencies for the stored-character total; stored markup is included, and server results can be cached for one hour. `find_transcription_pages_by_character` locates pages by one Unicode code point on newer servers. Permission failures remain errors; an absent or hidden endpoint is not interpreted as an empty result. See [docs/TRANSCRIPTION-API.md](docs/TRANSCRIPTION-API.md).

## Imports (0.12.0)

`submit_document_import` accepts a `source` with one of five `kind` values:
`pdf_file`, `xml_file`, `iiif_url`, `mets_file` or `mets_url`. Files must exist on
the MCP host; eScriptorium fetches remote URLs under its own network policy.
PDF/IIIF import images. XML/ZIP can select a layer by `transcription_id` or `name`.
METS `name` or `prefix_transcription_id` supplies a prefix for separate source
layers, rather than one exact destination layer. IIIF support is Presentation 2.

Imports may replace images/text even with `override=false`. XML override deletes
existing geometry and attached text/history across layers. Standalone XML matches
existing original filenames; unmatched pages produce warnings. Inspect reports
before declaring completion, including separate image-conversion work.

Optional `track=true` returns unconfirmed new group candidates and preserves
accepted status if monitoring fails. `get_import_status` optionally filters by
`group_id`; it has no native page-progress counters. Cancellation still targets
the latest import and does not roll back changes. The existing
`import_document_file` remains available on its original endpoint. See
[docs/IMPORTS-API.md](docs/IMPORTS-API.md) for source fields, layer visibility and
format limits.

## Pages and images (0.11.0)

`list_pages` accepts optional name and ordering filters. Name searches both page names and original filenames. `get_page_by_order` uses a zero-based position and safely follows the native page-detail redirect; page order and page ID are different values. Native extra page/region fields remain available.

`rotate_page` accepts a nonzero integer angle from -359 to 359; positive is clockwise. `crop_page` takes integer corners within the current image bounds. Both perform synchronous image work and can partially change files/rows before failing. Re-read after errors instead of retrying blindly.

Cropping overwrites the image. It translates line/region geometry without clipping it, leaves image annotations and character graphs unchanged, and does not refresh thumbnails. Rotation transforms line/region/image-annotation geometry but also leaves character graphs unchanged. Neither operation promises complete preservation of every coordinate-based annotation.

`bulk_move_pages` verifies all selected page IDs. The server retains their existing relative order; `move.index: -1` appends, and other indexes refer to the original page order. `update_page` adds original filename and stored confidence-summary metadata, with document typology checks.

`replace_page_image` targets an existing page and records uploaded bytes. It retains segmentation/text without resizing their coordinates and does not run upload's thumbnail/conversion hooks. Ordinary `upload_page` can replace a page with the same original filename. See [docs/PAGES-API.md](docs/PAGES-API.md) for full contracts and limitations.

## Segmentation (0.10.0)

`get_line` and `get_region` read individual page elements. Line creation supports a baseline, a mask, or both. Line edits must leave at least one geometry. Lines accept external IDs and reading-order indexes; regions accept external IDs and supported `locked` settings. Locking is an editor preference and does not prevent API edits or deletion.

`bulk_create_lines`, `bulk_update_lines` and `bulk_delete_lines` use native endpoints. Creation can include text in document-owned layers. The MCP checks page membership, every selected line and supplied region/layer/type references. Bulk updates can partially apply; after an error, read affected lines before retrying. Preflight checks do not lock concurrent writers.

`merge_lines` replaces two to eight distinct baseline-bearing lines. The server determines text order from geometry and script. Originals are deleted, and transcription graphs, confidence and history are not preserved. Bulk deletion also removes attached text and history. Returned deleted records are not a complete recovery archive.

`regenerate_line_masks` submits asynchronous work for all eligible page lines or a nonempty selection. Acceptance has no task ID and does not prove completion. `recalculate_line_order` synchronously replaces the page's reading order, including intentional manual ordering. See [docs/SEGMENTATION-API.md](docs/SEGMENTATION-API.md).

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
4. `upload_page` with an existing image path, or `submit_document_import` with the appropriate PDF/XML/ZIP/IIIF/METS source. The legacy `import_document_file` remains available.
5. For imports/conversion, check `get_import_status`, task messages and page workflow before processing further. A finished import may contain skipped-file warnings.

A page is a document part. IDs are positive primary keys, not page numbers. `move_page.position.index` is a **zero-based** position within the same document. Moving an entire document to another project uses `update_document.changes.project` with the destination slug.

### Correct text and segmentation

Read `list_lines`, `list_regions`, and `get_page_transcriptions`. Use `create_line_transcription` for a new line/layer combination, or `update_line_transcription` with the existing **line transcription record ID**, which differs from the segmented line ID.

Geometry uses pixel coordinates. A baseline needs at least two points; a polygon at least three. PATCH tools only send explicitly supplied fields. Explicit `null` can clear nullable fields, such as a line's region or polygon. Empty patches are rejected.

### OCR and training

1. `list_models`, or `upload_model` with a local Kraken model (`job: 1` for segmentation, `job: 2` for recognition).
2. Create/select a transcription layer.
3. `segment_pages` and `transcribe_pages` require explicit page IDs.
4. `train_recognition` requires a ground-truth layer and either a starting model or a new model name. `train_segmentation` requires at least two distinct segmented pages and a starting model or new name.
5. Optionally use `track: true` when submitting to receive candidate task groups, then inspect `get_training_report`, task reports and page workflow. Select document/group IDs explicitly; candidates are not confirmed model links.

Task report states: **0 queued, 1 running, 2 crashed, 3 finished, 4 canceled**. Successful job submission is not successful processing. OCR can replace text in its target layer; segmentation/training overrides can replace existing results. Cancellation uses dedicated server actions, not a manual change to the status field.

### Export transcriptions

`export_transcriptions` directly saves one layer as text or JSON to a new local file. It covers all pages by default, or explicit `parts`, and sorts pages and lines in reading order. JSON retains IDs and available revision/confidence metadata. The result includes path, byte count and SHA-256.

`request_server_export` supports native ALTO, PAGE XML, text and JSON document archives, plus OpenITI Markdown/TEI XML when enabled on the server. It accepts image inclusion and JSON options for metadata, annotations, all layers and ZIP/tar.gz containers. It checks the active layer, selected pages and region types before submitting. Omitted pages/region types mean all; an explicit subset remains a subset.

The development API exposes generated downloads. Use `list_downloads`, optionally filtered by `task_report_id`, then `get_download` and `download_generated_export` with the artifact fingerprint. File retrieval verifies identity and byte size through a fixed authenticated route; the advertised URL cannot redirect the request. `delete_download` removes its record and requests file removal, without deleting source documents. Older servers may lack this API; `download_export` still accepts completed same-server notification URLs.

Native JSON archives can include geometry, text/revisions, annotations and available images. They contain model metadata rather than weights and are not lossless database backups. Missing images may be skipped, all-layer exports include archived layers, and anonymization only changes selected author fields. There is no native JSON archive restore. Direct `export_transcriptions` JSON remains a separate single-layer export. See [docs/EXPORTS-API.md](docs/EXPORTS-API.md) for the full-document request example and limitations.

Acceptance returns no report/download ID. Inspect export task reports and warnings before declaring completion. An artifact's `task_report_id` links it to a report, but newly appearing records are not proof of submission attribution. Registration can fail after file creation, so a missing download row is not a reason to resubmit blindly.

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

Live checks use reads and local downloads/exports only. Mutation paths are tested with isolated fixtures; no live processing/training jobs are started for release verification. Actual OCR accuracy and training outcomes depend on installed server workers, models and training data. See [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) for the validation completed for each release.

API contracts are grounded in the live API and official [views](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/views.py), [serializers](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/serializers.py), and [import/export forms](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/imports/forms.py).
