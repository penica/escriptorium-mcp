# Changelog

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
