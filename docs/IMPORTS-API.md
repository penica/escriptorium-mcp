# Document imports API contract

Audited on 2026-09-16 using read-only development-server probes and upstream commit
`5f17889fe571d8fa25feb5deebec4221d9485d32`. Live OPTIONS confirms modern modes and
fields. The deployed container's exact commit is unverified; parser behavior below
is grounded in pinned source and isolated fixtures, not live import mutations.

## Sources and endpoints

`submit_document_import(document_id, source, track=false)` accepts exactly one
source variant. Local paths belong to the machine running the MCP server.

| `source.kind` | Required fields | Optional text options | Native request |
|---|---|---|---|
| `pdf_file` | `file_path` ending in `.pdf` | None; images only | Multipart `mode=pdf` |
| `xml_file` | `file_path` ending in `.xml` or `.zip` | `name` OR `transcription_id`; `override=false` | Multipart `mode=xml` |
| `iiif_url` | HTTP(S) `url` | None; images only | JSON `mode=iiif`, `iiif_uri` |
| `mets_file` | `file_path` ending in `.xml` or `.zip` | `name` OR `prefix_transcription_id`; `override=false` | Multipart `mode=mets`, `mets_type=local` |
| `mets_url` | HTTP(S) `url` | `name` OR `prefix_transcription_id`; `override=false` | JSON `mode=mets`, `mets_type=url`, `mets_uri` |

All variants POST once to **singular** `/api/documents/{D}/import/`; local files use
the `upload_file` field. Ordinary ZIP uses XML mode; a METS ZIP uses METS mode. File
contents and remote sources are validated by eScriptorium. Extension checks do
not prove a file contains a valid PDF/XML/archive. Extensions must be lowercase
because the native parser dispatch is case-sensitive.

The existing `import_document_file` retains its **plural** `documents/{D}/imports/`
route and original argument/response contract. It does not gain modern modes or
silently move to the new endpoint. On an older server without the modern route,
use the existing legacy file tool where appropriate; failed modern submissions
are never automatically retried through another route.

## Layer selection

XML/ordinary ZIP can select a document layer by `transcription_id`, or select/create
one by `name`. METS creates separate layers named **`prefix | source-layer`**: its
`name` is a prefix, and `prefix_transcription_id` selects an existing layer's name
as that prefix. It does **not** put all METS text in that exact layer.

Names must contain a non-whitespace character and be at most 256 characters, the
stored import-name limit. Selected layer names must meet the same limit even
though ordinary layer names may be longer. Omit unused name/ID options; explicit
nulls and simultaneous name/ID selections are rejected.

The MCP checks the document and a supplied layer through its scoped detail route,
including returned IDs, before submitting. That native detail route hides archived
layers, so an archived ID normally fails preflight with 404. A deployment that
explicitly returns an archived layer is allowed; the MCP never unarchives it.
An explicit name follows native parser name matching. The serializer saves a
selected layer's **name**, not a durable target ID: concurrent renames can change
the destination. Preflight is not a lock.

## Replacement and override behavior

Standalone ALTO/PAGE XML matches pages by `original_filename`. Missing matches
produce warnings; XML alone does not supply missing page images.

**`override=false` is not a no-overwrite guarantee.** Existing external IDs can
match and update regions/lines and replace target-layer text, with native revision
handling. PDF/ZIP/METS can replace images matching original filenames. IIIF can
replace images matching generated source URLs. Existing geometry is not guaranteed
to be resized or reprojected after image replacement.

**`override=true` deletes page lines and regions before XML import**, cascading
their text/history across all layers. Per-page database transactions do not make
an entire multi-page import atomic. Submission, import records and queueing also
do not form one guaranteed transaction. After a failed response or timeout,
inspect remote state before retrying; the MCP sends no automatic second POST.

## Acceptance, monitoring and cancellation

Modern submission returns HTTP 201 with `{"status":"ok"}` and no import/task/group
ID. The default tool returns that response unchanged. It means accepted, not
completed. Image conversion/thumbnail jobs can continue separately, and finished
import reports can contain skipped-file warnings.

Optional `track=true` wraps the raw result with `accepted=true` and compares visible
groups before/after submission. New groups matching `imports.tasks.document_import`
or an initially null method are **unconfirmed candidates**. Even a single candidate
is not proof of attribution. Tracking reports `none`, `candidate`, `ambiguous` or
`unavailable`; failed monitoring preserves accepted status and never resubmits.

`get_import_status(document_id, group_id=...)` optionally limits report history to
a caller-selected document group. It cannot prove that group belongs to a given
submission. Without a group it includes historical imports. Task visibility is
limited to the authenticated user. Native import `processed`/`total`, workflow
state and import-record errors are not exposed as REST records; report percentages
must not be presented as page progress. Empty history does not prove no import.

`cancel_document_import` still targets the latest native import, not an arbitrary
group/import ID. Cancellation before a task report is attached may fail to prevent
queued work from starting. It neither rolls back imported pages nor guarantees an
immediate stop. Already-stopped/missing-import errors remain errors.

## Format and server limits

- **IIIF:** The audited parser supports Presentation 2 `sequences[0].canvases`, with
  the first image's `resource.service.@id`. It does not implement Presentation 3
  `items` or arbitrary direct-image resources. It imports all canvases; quality
  comes from server configuration. No invented page-range/quality option is sent.
- **METS:** Remote descriptors resolve relative references from their URL's
  directory. Plain uploaded XML has no supplied base URI; use absolute references
  or a self-contained METS ZIP. A ZIP must contain a namespace-bearing METS
  descriptor and its referenced files.
- **Network access:** eScriptorium fetches manifest/descriptor/image URLs. The MCP
  never downloads source URLs or forwards its API key to source hosts. Server
  domain/address/redirect policy still applies, including private-address limits;
  the MCP does not bypass it.
- **Not exposed:** No native JSON document-archive restore, import-record CRUD,
  chunked upload, arbitrary import-ID cancellation or modern resume option exists
  in the audited routes. `.json` is interpreted as IIIF, not a full-document backup.
  The legacy form's latest-failed-import resume has unsafe missing/nonfailed-record
  edge cases and is not exposed as automatic retry or recovery.

## Pinned sources

- [API routes](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/urls.py), [views](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py) and [serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py): modern/legacy routes, layer visibility, modes, group creation and acceptance.
- [Import parsers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/parsers.py) and [fetch policy](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/fetch.py): formats, replacement, prefixes and source URL validation.
- [Import models](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/models.py), [tasks](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/tasks.py) and [legacy form](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/forms.py): stored progress, report attachment, cancellation and legacy resume.
