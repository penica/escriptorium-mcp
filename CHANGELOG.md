# Changelog

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
