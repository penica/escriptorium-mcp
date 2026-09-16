# Exports and generated downloads API contract

Audited on 2026-09-16 against development-server GET/OPTIONS responses and upstream
commit `5f17889fe571d8fa25feb5deebec4221d9485d32`. The deployed container's exact
commit is unverified. No live export or deletion was performed. The inspected
account had no generated downloads, so successful file retrieval is verified with
isolated fixtures, not an existing research artifact.

## Native export requests

`request_server_export(document_id, export)` queues one native export through
`POST /api/documents/{D}/export/`. Existing ALTO, PAGE XML and text calls keep their
arguments, default ALTO format and raw `{"status":"ok"}` acceptance response.

| Export field | Meaning |
|---|---|
| `transcription` | Required visible, active document layer, even with all layers selected |
| `file_format` | `alto`, `pagexml`, `text`, `json`, `openitimarkdown` or `teixml` |
| `parts` | Nonempty distinct page IDs, or omit for all pages |
| `region_types` | Nonempty distinct enabled block IDs and/or `Undefined` / `Orphan`; omit for all |
| `include_characters` | Character geometry for ALTO/PAGE/JSON; existing text calls may supply it but text ignores it |
| `include_images` | Include available images in ALTO/PAGE/JSON |
| `include_metadata` | JSON document metadata; page metadata is included independently |
| `include_models` | JSON model catalogue metadata, not weights or checkpoints |
| `all_transcriptions` | JSON includes all layers, including archived layers |
| `include_annotations` | JSON image/text annotation records |
| `anonymize` | JSON pseudonymization of selected author fields |
| `archive_format` | JSON archive container, `zip` or `tar.gz`; native default ZIP |

New flags default to false. JSON-only flags cannot be enabled for another format,
and explicit `archive_format` is restricted to JSON. Image inclusion is restricted
to formats that use it. Legacy null `parts`/`region_types` still mean omission;
explicit empty lists are rejected. New nonnullable options reject explicit null.

OpenITI Markdown and TEI XML require server-side feature flags and are normally
disabled. Disabled formats return the native validation error, without a fallback
to another format. The action's OPTIONS response describes the document serializer
and does not reliably advertise these export choices.

The MCP verifies the document identity, selected active layer, supplied page IDs
and enabled block types before sending one POST. Omitted region types include all
document-enabled types plus `Undefined` and `Orphan`; an explicit subset stays a
subset. Preflight does not lock concurrent edits. Failed requests or timeouts may
leave queued work; inspect task reports before retrying.

## A native full-document JSON archive

Use the following `export` object with an actual active layer ID, omitting `parts`
and `region_types` to cover the whole document:

```json
{
  "transcription": 5,
  "file_format": "json",
  "include_images": true,
  "include_characters": true,
  "include_metadata": true,
  "include_models": true,
  "all_transcriptions": true,
  "include_annotations": true,
  "anonymize": false,
  "archive_format": "zip"
}
```

Native JSON archives contain `document.json`, `export-config.json`, `parts.jsonl`,
optional `annotations.jsonl` and requested available images. Page records include
geometry, ordering, type identities, text, confidence and revision information.
Character graphs are optional. ZIP and tar.gz contain the same logical records.

This is a research archive with specific limits:

- Model inclusion contains IDs/names/jobs only. Download model files/checkpoints
  separately when weights are needed.
- Full ontology configuration, taxonomy/component definitions, colors, sharing
  settings and other database fields are not completely represented. Native
  ontology YAML is a separate export.
- Missing or inaccessible image files can be skipped by the native collector.
  Completed generation does not prove every original scan is present.
- All-layer selection includes archived layers, but export configuration does not
  preserve their archive-status flags.
- Anonymization changes selected author fields. Names in text, filenames,
  comments, metadata or annotation values remain; identifiers remain too.
- `include_metadata=false` does not remove page metadata in the audited exporter.
- The archive has no native cryptographic completeness manifest or restore API.
  It is not a lossless database backup and cannot be round-tripped through the
  current document-import tools.

The existing `export_transcriptions` JSON is a direct single-layer export with
page/line records. It is separate from this native document archive.

## Completion and attribution

Submission returns HTTP 200 without a task, report, group or download ID. This
native action creates no task group. Monitor existing `list_tasks` with the local
method filter `imports.tasks.document_export`, and inspect report messages for
skipped-page warnings. Acceptance and a finished report do not prove completeness.

Generated-download metadata has `task_report_id`, which links that artifact to a
report when present. It does not prove which client submission caused the report.
New timestamps or a single matching candidate do not establish that attribution.

Download registration can fail after the task has finished, leaving a valid file
and notification but no download row. Existing `download_export` remains useful
for a completed same-server notification URL. Missing download metadata is not a
reason to resubmit automatically. Older servers may lack the downloads API.

## Generated-download tools

| Tool | Native route under `/api/` | Behavior |
|---|---|---|
| `list_downloads(task_report_id?)` | GET `downloads/` | Fully paginated current-user records; optional report filter is applied locally |
| `get_download(fingerprint)` | GET `downloads/{fingerprint}/` | Owned metadata, including expiry/access information |
| `download_generated_export(fingerprint, destination)` | GET metadata, then `downloads/{fingerprint}/file/` | Stream verified bytes to a new MCP-host file |
| `delete_download(fingerprint)` | DELETE `downloads/{fingerprint}/` | Delete the record and attempt server-file removal |

Fingerprints are exactly 32 lowercase hexadecimal characters, not numeric IDs.
Foreign or missing records normally return 404. Expired metadata may remain
visible even when its file endpoint returns 404. Native zero sizes/counts, null
expiry/report IDs and future metadata fields are preserved.

The list endpoint has no native document/report/search filters. Pagination follows
only the configured downloads collection on the configured origin/API prefix;
foreign targets, other paths, redirects and loops are rejected.

File retrieval verifies metadata identity and nonnegative advertised size, then
uses the fixed API file route. The returned `file_url` never controls where the
authenticated request goes. Redirects are refused. File GET updates server access
counters, so it is not represented as a side-effect-free metadata read.

Destination paths belong to the MCP host, including over HTTP. Files must be new,
use portable names and stay outside the configured Books archive. Streaming uses
an exclusive `.part` file, checks metadata size and applicable Content-Length, and
publishes only after successful transfer. Existing destination/partial files are
never overwritten. Failed transfers retain partial files for diagnosis. Returned
byte counts and SHA-256 verify downloaded bytes, not source completeness or a
server-provided authenticity signature.

Deletion sends one DELETE and preserves bodyless 204 success. It does not delete
the source document, pages or models. Upstream swallows some file-unlink failures,
so record deletion does not guarantee physical or secure erasure. There is no
download-record update or arbitrary upload operation.

## Pinned sources

- [Export form](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/forms.py), [exporters](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/export.py) and [tasks](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/tasks.py): request options, archive contents, job/report and registration behavior.
- [Views](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py), [serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py) and [reporting models](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/reporting/models.py): ownership, fingerprints, retention, file counters and deletion.
