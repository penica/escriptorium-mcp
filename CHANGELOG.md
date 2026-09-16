# Changelog

## 0.16.0 — 2026-09-16

### Module 11: Alignment and textual witnesses

Added eight tools for owned reference-text management, safe local download,
ordinary reference alignment and forced character alignment; 160 tools total.
Witness file operations validate nonempty UTF-8 text while preserving original
bytes. Downloads use existing portable storage and checksum reporting.

Standalone native upload requires explicit acknowledgment of the audited
upstream owner-assignment defect. Native acceptance is retained separately from
bounded ownership-readback evidence; inaccessible or malformed results do not
cause retries, hidden alignment jobs or automatic cleanup.

Ordinary alignment exposes all supported form options and coherent beam/offset
search modes, with explicit native defaults and preserved zero values. Scope
checks cover active sources, pages, region types and existing owned witnesses.
Target names are normalized and source-name reuse is rejected. Required target
reuse acknowledgment covers hidden archived collisions that the API cannot
enumerate. Direct reference uploads use the native owned alignment-upload path.

Forced alignment accepts native-supported archived layers through the action's
document-scoped validation and replaces character graphs, not text or geometry.
Both actions submit once. Optional ordinary-alignment group tracking preserves
acceptance after monitoring failure and labels all inferred groups unconfirmed.

Documentation explains target reuse, merge/full-document scope, partial effects,
missing execution prerequisites and cancellation limits. A private single-attempt
request option bounds mutations and diagnostic reads without changing existing
requests. Version, installer, bundled skill and generated catalogue are updated
together; release testing does not modify live research content or services.

Release validation correction: authenticated HTTP tests now use the MCP SDK's
bounded request budget and cover a slow alignment preflight. This fixes a
five-second test-client timeout on Windows; runtime code and version are unchanged.

## 0.15.0 — 2026-09-16

### Module 10: Virtual collections

Added eight collection tools, bringing the catalogue to 152: owned collection
listing/detail/creation/update/deletion, complete membership reads, recognition
training and segmentation training across documents. Typed memberships validate
each page and layer in its supplied document. Default transcription preferences
remain separate from membership. Omitted selections are preserved; empty arrays
or maps explicitly clear them. No per-item delta operation is invented.

Collection pagination follows every page within the original route, rejects
redirects and unsafe next links, and preserves native response fields. These
strict transport checks are opt-in, preserving existing worker requests.

Training validates all current members, model identity/job and owned idle
overwrite targets. Recognition requires one page; segmentation requires two.
Native acceptance and model IDs are preserved without inventing task-group links
or completion. Membership is resolved again at execution time. Partial-write and
uncertain-submission errors never cause an automatic mutation retry.

The collection guide explains native non-atomic writes, deletion scope, model
clone/overwrite behavior, missing collection task-group routes and unsupported
D-FINE finetuning. Version, installer, bundled skill and catalogue/schema are
updated together. Live checks remain read-only; mutations use isolated fixtures.

## 0.14.0 — 2026-09-16

### Module 9: Projects, documents and metadata

Added 15 tools for project settings, native document statistics/page lookup,
document/page metadata associations and personal/project tag definitions;
144 tools total. Existing project/document tools gain typed search/filter/sort,
512-character names, guidelines, confidence visualization and scoped complete
tag assignments. Empty arrays clear assignments; omitted fields stay omitted.

Project/document reads now preserve native extra fields, expanded sharing/tag
objects, nulls, zeroes and timestamp strings. This fixes older connector DTOs
discarding new fields or rejecting populated modern objects. Existing argument
names and collection/detail shapes remain; synthetic DTO defaults are no longer
added and fully followed pagination ends with next=null.

Metadata value edits are separate from the explicitly named global shared-key
operation. Association deletion preserves shared keys and other records; tag
definition deletion unassigns that definition throughout its scope. Document
tag assignments are checked against the effective target project, including
project moves, before mutation. Project deletion documentation states its native
document/content cascade. Preflight is not a lock or a transaction guarantee.

The record guide, bundled skill, version, installer and generated catalogue/schema
are updated together. Release verification uses isolated mutation fixtures and
read-only live probes; no running service or live research records are changed.

## 0.13.0 — 2026-09-16

### Module 8: Exports and downloads

Added four generated-download tools, bringing the catalogue to 129: list owned
downloads with optional local report filtering, inspect metadata, retrieve a file
by fingerprint, and delete a download record. Collection reads fully paginate
within the configured downloads route. File retrieval uses a fixed authenticated
route, verifies metadata identity and byte size, and never trusts `file_url` as a
request target. Redirects, pagination loops and cross-route links are rejected.

Expanded `request_server_export` with native JSON archives, optional server-enabled
OpenITI Markdown/TEI XML, image inclusion and JSON metadata/model/all-layer/
annotation/anonymization/container options. Existing basic export calls and raw
acceptance responses remain compatible. Scoped checks validate documents, active
layers, selected pages and enabled region types before one submission.

Streaming downloads retain portable, exclusive destination handling outside the
Books archive, preserve failed partial files and report bytes/SHA-256 after
publication. Download deletion preserves native bodyless success without claiming
guaranteed physical erasure. Expired records and missing files remain errors at
retrieval; access counters are acknowledged as a file-download side effect.

Documentation distinguishes a direct layer JSON export from a native document
archive. Native archives contain model metadata rather than weights, can omit
missing images, and do not provide full database backup or JSON restoration.
Anonymization has limited scope. Export submissions return no report/download ID;
an artifact's report link does not establish client-submission attribution.

Version, installer, generated catalogue/schema, bundled skill and the
[export/download contract](docs/EXPORTS-API.md) are updated together. No live
exports, download deletions or service deployment are performed during validation.


## 0.12.0 — 2026-09-16

### Module 7: Imports

Added `submit_document_import`, bringing the catalogue to 125 tools. A typed source
selects PDF, XML/ordinary ZIP, IIIF URL, local METS XML/ZIP or remote METS URL. The
tool maps each source to the modern singular import endpoint, using multipart
uploads or JSON URLs without fetching remote sources on the MCP host.

XML can select a document layer by ID or name. METS exposes layer-name prefixes,
including a prefix selected from an existing layer, without claiming an exact
target layer. Scoped preflight validates returned identities and import-name
limits. Contradictory sources/targets, missing files, wrong extensions, unsupported
URL schemes and explicit null names/IDs are rejected before writing.

Optional tracking returns unconfirmed task-group candidates while preserving raw
acceptance by default. Failed optional monitoring never erases acceptance or
resubmits. `get_import_status` gains a caller-selected group filter. The shared
group reader is reused by training without changing its submission contract.

The legacy file-import tool keeps its original endpoint and arguments. Updated
descriptions explain latest-import cancellation races, replacement with override
off, all-layer geometry/text deletion with XML override, IIIF Presentation 2 and
METS prefix/reference limits. No native progress counters, archive restore or
automatic resume are invented. No live imports or service deployment are performed.

Package/server versions, installer, generated tool catalogue/schema, bundled skill
and [import contract](docs/IMPORTS-API.md) are updated together.


## 0.11.0 — 2026-09-16

### Module 6: Pages and image operations

Added five tools, bringing the catalogue to 124: page lookup by zero-based order,
rotation, cropping, bulk page moves and explicit image replacement. Page listing
adds server-side name/original-filename substring filtering and ordering. Page
metadata adds original_filename and max_avg_confidence with native null/length
constraints and document-assigned typology checks.

Lookup permits one validated same-origin, same-document redirect and treats native
200 error objects as failed lookups. Page pagination rejects foreign origins,
redirects and loops while preserving the existing unfiltered result shape and
new native fields. Generic REST redirects remain refused.

Image operations check current page scope/bounds and send one native mutation.
Rotation accepts nonzero integer angles from -359 through 359. Crop requires an
in-bounds integer rectangle. Partial failures are reported without automatic retry.
Crop overwrites pixels and leaves annotations/character graphs unchanged; rotation
transforms image annotations but leaves character graphs. These limits and native
thumbnail behavior are documented, without inventing corrective background jobs.

Bulk moves reject incomplete or duplicate selections and preserve native relative
ordering/index semantics. Image replacement records real uploaded byte size and
keeps existing text/geometry without reprojection. Upload documentation now states
that a matching original filename may replace an existing page; its MCP annotation
now correctly marks upload as potentially destructive and non-idempotent.

Version, installer, catalogue/schema, skill and contract documentation are updated.
See [docs/PAGES-API.md](docs/PAGES-API.md) for pinned upstream evidence and limits.
No live images or running service are changed during release verification.


## 0.10.0 — 2026-09-16

### Module 5: Segmentation

Added eight tools, bringing the catalogue to 119: individual line/region reads,
native bulk line create/update/delete, merging, mask regeneration and automatic
reading-order recalculation. Existing geometry tools gain mask-only line creation,
nullable baseline edits, external IDs, line order and supported region locking.
Explicit locking checks writable metadata to avoid silent ignores on older servers.

Preflight verifies page ownership and every selected line, supplied page region,
document layer and assigned typology. Nested text receives the newly created line
ID from the server. Duplicate selections, cross-page moves and edits leaving no
geometry are rejected. Bulk update uses one native PUT and explains partial
application on failure; it is never retried automatically.

Merge requires two to eight distinct baseline-bearing lines. The server combines
text in geometric/script order, deletes originals and does not preserve graphs,
confidence or history. Bulk line deletion removes attached text/history. Mask
regeneration reports queued acceptance without inventing a task ID; automatic
order recalculation returns the synchronous page result. Region locking is an
editor preference, not access control.

Package, installer, catalogue, skill and documentation are updated together. See
[docs/SEGMENTATION-API.md](docs/SEGMENTATION-API.md) for contracts and compatibility.
Live verification remains read-only; no service deployment is included.


## 0.9.0 — 2026-09-16

### Module 4: Transcriptions

Added eight tools, bringing the catalogue to 111: native bulk create/update/clear
for line transcriptions, individual line-text and layer retrieval, layer settings,
stored-character statistics and character-to-page lookup. Page-text listing adds
an optional layer filter. Line creation and edits expose nullable graphs and
average confidence; reference-changing edits validate page/document membership.

Bulk preflight follows pagination and verifies page, line, layer and record scope,
rejecting duplicate IDs/pairs and reference changes that collide with unchanged
records. Native update uses PUT once and reports possible partial application on
failure. Native clear blanks content only, retaining rows, graphs, confidence and
existing history without adding a revision. The existing layer deletion tool's
description now accurately states archive/rename semantics and manual protection.

Statistics preserve server counts/order and Unicode. Counts include stored markup
and can be cached for one hour. Character lookup requires one Unicode code point,
verifies the parent layer first and distinguishes unavailable/hidden endpoints
from permission failures. Server normalization, explicit nulls and omitted fields
are preserved. No live transcriptions were modified during verification.

Re-audited the upgraded development deployment: character lookup, native ontology
YAML, fonts, downloads, virtual collections and region locking are now available.
Other modules retain their roadmap order; Python runtime migration is separate.
Package, installer, skill and API documentation are updated together. See
[docs/TRANSCRIPTION-API.md](docs/TRANSCRIPTION-API.md) for source contracts,
non-atomic behavior, schema limitations and compatibility details.

## 0.8.0 — 2026-09-16

### Module 3: Training and evaluation

Added `get_training_report`, bringing the catalogue from 102 to 103 tools. It returns model training state, raw validation scores, current-file references and checkpoint metadata, with optional caller-selected document/group task summaries filtered to the model's training method. Group selection requires a document ID. Caller-selected task/model relationships are labeled explicitly; document-only summaries include historical training reports. Missing values, zero values and repeated checkpoint paths are preserved. Idle state does not establish success, and file availability is not inferred from an advertised reference.

`train_recognition` and `train_segmentation` add optional `track`, defaulting to false for the existing raw response shape. Tracked submission reads document groups before and after one POST, preserves the upstream acceptance response and reports zero/one/multiple matching candidates or unavailable monitoring. New groups whose method is initially null remain candidates. Even one candidate is not confirmed attribution; concurrency and delayed reports prevent a guaranteed link. Optional monitoring failure preserves acceptance and never triggers automatic resubmission.

Training inputs now reject duplicate page IDs and explicit null model/name options, and accept model names up to 256 characters. Selected models are checked for the appropriate segmentation/recognition job. Overwriting requires model ownership and an explicitly stopped training state, including calls that also supply `model_name`. These reads are preflight observations rather than atomic locks. Page and recognition-layer membership remain authoritative server-side serializer validation.

### Compatibility and limits

The standard document-training API returns acceptance without a model, task or group ID. All supported request fields remain available; unsupported hyperparameter keys are not invented. The audited API has no independent evaluation endpoint or training request controls for epochs, learning rate, optimizer, batch size, precision, device or validation split. Validation-score meaning depends on the model/server; this release does not calculate or relabel it as CER/WER. Custom ARC controls and virtual-collection training are separate from this contract.

Package/server/installer versions, generated tool catalogue/schema, training API documentation and the bundled agent skill are updated together. See [docs/TRAINING-API.md](docs/TRAINING-API.md) for contract evidence and [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) for completed validation and publication status.

## 0.7.0 — 2026-09-16

### Module 2: Model management

Six new tools bring the catalogue from 96 to 102 tools:

- `update_model`: selectively rename or edit owned models' job/storage-size metadata; reject empty updates and explicit nulls. Names allow up to 256 characters.
- `replace_model_file`: upload replacement weights with multipart PATCH and update byte-size metadata. This does not create a checkpoint backup.
- `delete_model`: delete an owned, idle model and its server-managed relationships while preserving document transcriptions.
- `list_model_versions`: expose checkpoint revision IDs, file references and available server-specific training metrics without discarding additional fields.
- `get_model_documents`: expose associated document IDs with an explicit read-only capability result.
- `download_model`: download an advertised current file or selected checkpoint to a new MCP-host path, reporting byte count and SHA-256 only after completion.

`list_models` now accepts server-supported document and numeric job filters while preserving no-argument calls. Existing numeric public job inputs remain **1 = segmentation** and **2 = recognition**; upload and metadata writes now serialize the API's required `Segment`/`Recognize` labels. Multipart dispatch now honors PATCH for replacement files instead of always using POST.

The three new mutation tools require `rights == "owner"`. File replacement, deletion and job/size edits also require `training == false`; renaming remains available during training. Omitted or unknown ownership/training evidence does not authorize restricted changes. These preflight checks do not provide an atomic server-side lock.

Downloads use the existing authenticated transfer worker, enforce the configured origin, reject redirects and unsafe/ambiguous checkpoint paths, refuse existing output or partial files and exclude the scan-only Books archive. Missing advertised files remain errors and never produce a reported completed download. Checkpoint revision selection must match exactly one advertised version.

### Compatibility and limits

The audited ARC and upstream master/v26.07 REST serializers expose document associations as read-only. No bind/unbind or checkpoint revert/delete REST action exists; those operations are not represented as working API tools. Processing/training can create associations as a side effect, and the eScriptorium UI provides unbinding. Changing job metadata does not convert weights. Download an original file/checkpoint before replacing or deleting it when it must be retained.

Package/server versions, WSL installer references, tool catalogue/schema, model API documentation and the bundled agent skill are updated together. The release builder includes the model API and releasing guides in the transfer archive. See [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) for completed validation and publication evidence.

## 0.6.0 — 2026-09-16

### Module 1: Tasks and job monitoring

Seven new tools bring the catalogue from 89 to 96 tools:

- `list_document_tasks`: document task totals, last-start timestamps and server-supported name/state/staff-user filters.
- `list_task_groups` and `get_task_group`: paginated groups, state buckets, timestamps and associated-page counts.
- `get_document_job_status`: authenticated-user report summaries, optional group selection, failure messages and explicit completion semantics.
- `get_import_status`: import report history and status without unsupported processed/total estimates.
- `cancel_document_tasks` and `cancel_document_import`: explicit document-wide cancellation and dedicated latest-import cancellation.

`list_tasks` adds document/group/date ordering and local state/exact-method filters. Local filters follow all pages before matching; unsupported state/method query parameters are never sent to eScriptorium. Calls without arguments retain the existing API response shape. Locally filtered results use a results envelope with the matched count.

Summaries distinguish terminal reports from success. Failed/canceled reports count toward `terminal_percent`; only a nonempty, exclusively Finished set sets `all_finished`. Empty and unknown states cannot indicate success. Document/group access is verified before returning a summary. Upstream report fields, including messages and timestamps, are preserved.

The existing `cancel_task` description and skill now disclose upstream document-wide training/import cleanup side effects even when one report ID is supplied. Dedicated model/import cancellation remains available. This release does not change those upstream semantics or modify live eScriptorium jobs during verification.

Package/server versions, tool schemas, WSL installer references and the bundled agent skill are updated together. See [IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) for validation and release evidence.

### Compatibility and limits

Compatible monitoring routes were checked against the deployed ARC API and upstream master/v26.07 source. Report listings are restricted to the authenticated user; group/document aggregate visibility follows upstream permissions. Import status comes from task reports because import submission endpoints do not expose native import-record status. No percentage is claimed for an individual running job. Version 0.6.0 preserves both STDIO and authenticated Streamable HTTP transports.

## 0.5.0 — 2026-09-16

Initial public repository baseline: 89 tools, including ontology/annotation management, repair and merge previews, portable schema snapshots and capability-gated native ontology operations. Includes macOS, Windows and Linux support, STDIO and authenticated Streamable HTTP, WSL deployment assets and the eScriptorium agent skill. Detailed baseline coverage is in [ONTOLOGY-COVERAGE.md](ONTOLOGY-COVERAGE.md).
