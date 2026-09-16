# Post-1.0 MCP roadmap

Saved: 2026-09-16. Status: **first additive batch implemented; release integration complete**.
This is the continuation roadmap for the completed [module expansion](MODULE-ROADMAP.md).
Use it when the user asks to resume work on the remaining API gaps.
Saving this roadmap does not start implementation, publish a release, schedule
monitoring or deploy an update.

## Baseline and evidence

- MCP **1.0.0**, 175 tools; release commit `65afe4e6f1cf918399534f641f741c18383d10f3`.
- MCP **1.1.0** release candidate, 176 tools; MCP-01 and MCP-02 implemented
  additively, with publication still pending.
- [Coverage audit](docs/API-COVERAGE.md) and [operation map](docs/API-COVERAGE.csv):
  107 paths, 213 operations; 179 covered routes, 24 PATCH alternatives to PUT,
  and 10 operations not exposed directly.
- [1.x compatibility policy](docs/STABILITY.md) governs all changes.
- The exact deployed eScriptorium commit is unverified. Refresh live schema and
  relevant GET/OPTIONS metadata before implementing an item; schema metadata
  alone is not proof of action semantics or successful writes.

## Ordered backlog

| Order | ID | Item | Status | Completion outcome |
|---|---|---|---|---|
| 1 | MCP-01 | Optional bounded/paged list reads | Implemented | Supported lists share a strict native-page contract; omission preserves all-results defaults and local-filtered global totals remain unknown. Publication is pending. |
| 2 | MCP-02 | Script lookup by ID | Implemented | `get_script` reads native script detail; focused tests and live identity readback passed. Publication is pending. |
| 3 | MCP-03 | Document training-cancellation shortcut | Deferred | Existing `cancel_model_training(model_id)` is precise; the document action selects the last training model and does not replace it. |
| 4 | MCP-04 | Legacy import recovery | Upstream required | No stable target import ID or import-record reads exist; latest-failed resumption and timeout/duplicate/partial-write reconciliation are not reliable contracts. |
| 5 | MCP-05 | Credential setup and token rotation helper | Deferred | Existing hidden-key installer/manual configuration is sufficient; no operational need for an account-password/token-rotation command was established. The optional admin-helper decision remains conditional pending a later user selection. |
| 6 | MCP-06 | Creation and collection-edit conveniences | Deferred | Existing create-then-update and full-membership replacement workflows cover the known cases; no recurring need for a convenience wrapper is established. |

**Next item on resume:** choose a deferred item only when an operational need
justifies it, or re-audit MCP-04 after upstream adds reliable import records.
Optional and audit-first items are not promises to implement unsafe or unusable
native behavior. Record the decision and evidence before moving them to Ready.
No publication date is assigned until scope and validation are settled. The
first batch is prepared as **1.1.0**; publication remains pending. This update
records implementation and release-integration evidence; it does not mark a
GitHub release or deployed service.

## MCP-01: optional bounded/paged list reads

**Goal:** make large catalogues and task histories manageable without changing
existing callers or silently truncating their results.

Scope:

- Start with one explicit opt-in native page contract using strict `page` and
  `page_size` inputs. Do not forward unsupported `paginate_by` parameters.
- Inventory list tools and backend pagination support across documents, pages,
  tasks, models, projects, transcriptions, annotations, metadata, tags,
  collections, witnesses, users, groups, fonts and downloads.
- Preserve the current default, result envelope and existing filter behavior;
  an omitted bound continues to retrieve all results.
- Local filtering/search is confined to the page returned by the native request.
  If the native envelope cannot provide a filtered global count, report that
  total as unknown rather than treating the returned page count as complete.
- Define how bounded retrieval interacts with local filters/search. A filtered
  page is not the complete filtered dataset; counts and continuation information
  must accurately describe their scope.
- Preserve same-origin/path validation, loop detection and error propagation.
  Return only validated continuation information, never an arbitrary-URL fetch API.
- Internal audits, exports, repairs and aggregate job summaries must still retrieve
  complete selections where correctness depends on them.

Completion criteria:

- Demonstrate first, middle, final, empty and invalid pages, with supported and
  unsupported page-size behavior covered.
- Verify local-filter semantics, changing collections, unknown totals and the
  distinction between returned count and full native count.
- Existing unbounded calls keep their behavior; opting into a bound demonstrably
  limits retrieval and output.
- Update the tool schemas, reviewed stability baseline, relevant guides and skill.

## MCP-02: script detail

Native route: `GET /api/scripts/{id}/`.

- Add `get_script(script_id)` with a strict positive identifier and read-only
  annotation; preserve native fields and normal missing/permission errors.
- Retain `list_scripts` unchanged. Document that document creation uses the script
  **name**, while this lookup uses its **ID**.
- Verify through actual MCP discovery and a successful detail read, plus invalid,
  missing and denied IDs using fixtures as appropriate.

The 2026-09-16 audit confirms the native script-detail route in the live schema.
The implementation includes `get_script`; focused strict-ID, native-error,
list-preservation and discovery/detail verification passed. Package integration
is complete, so this item is Implemented but remains unpublished.

## MCP-03: document training cancellation

Native route: `POST /api/documents/{id}/cancel_training/`.

- Recheck deployed behavior before deciding to add the shortcut. The audited source
  selects the last currently training model associated with the document.
- It must not be described as canceling every model or as atomically selecting a
  model observed by a preceding read. `cancel_model_training(model_id)` remains
  the precise existing alternative.
- If implemented, send one request, preserve native failure/no-training behavior,
  and distinguish accepted cancellation from observed termination. Never retry
  an uncertain write automatically.
- Verify multiple active models, no active model, permission denial and timeout
  behavior with isolated fixtures. Live cancellation requires an authorized
  disposable job; do not cancel a research training run for verification.

Decision allowed: **Deferred: existing model cancellation is sufficient**.

## MCP-04: legacy import recovery audit

Potential option: `resume_import` on the plural `/documents/{id}/imports/` form.
The modern singular `/documents/{id}/import/` action has no resume field.

Audit deliverable:

- Identify the selected failed import, missing/nonfailed-record behavior, retained
  input-file availability, queue/report behavior and duplication/partial-write risks.
- Determine whether the caller can reliably identify the intended import and
  whether a timeout can be reconciled without another submission.
- Compare deployed source with the pinned contract; use isolated fixtures and,
  only within authorization, disposable failed imports for behavior verification.

Implementation gate: a useful, predictable recovery contract must exist. Otherwise
record **Upstream required**, with the exact missing guarantees. Do not relabel
resubmission as resume or add an automatic retry to existing import tools.

## MCP-05: credential setup/rotation helper

Native route: `POST /api/token-auth/`; source additionally accepts `regenerate`.

- Prefer installer/administration tooling over a general conversational MCP tool.
- Keep password entry hidden and out of arguments, logs, reports and examples.
- Distinguish the eScriptorium API key from the MCP HTTP bearer token.
- Design configuration persistence, permissions, failure recovery and service
  lifecycle handling before implementing rotation. Once the old token is revoked,
  a configuration backup alone cannot restore its validity.
- Verify obtaining an existing token separately from rotation, and test storage
  failures without rotating the production credential.

Decision gate: confirm an actual setup/rotation need when this item is selected;
existing manually configured keys already work. This item is deferred pending
such a need; the optional admin-helper question remains available for a later
selection and is not an implementation commitment.

## MCP-06: optional workflow conveniences

These are not missing end-to-end REST capabilities:

- Additional create-time page metadata and transcription-layer settings, where
  current create-then-update calls already provide the result.
- Add/remove collection members without requiring callers to construct an entire
  replacement selection. Any read/modify/write helper must disclose non-atomicity
  and preserve unrelated members; do not promise conflict-free concurrent edits.

Implement only where a recurring workflow justifies the extra public surface.
Retain the current direct update/replacement tools and their meanings.

## Deliberately excluded from the ordinary backlog

| Gap or restriction | Decision | Condition for reconsideration |
|---|---|---|
| Task-report/group create, edit and delete | Keep excluded; history CRUD is not job control, and group fields are read-only in live metadata. | A specific administrative repair need and a verified, bounded contract. |
| Raw project `ontology_config` JSON writes | Prefer native validated ontology import/export/delete. | A capability that cannot be expressed through the existing template workflow. |
| Cross-page geometry/annotation reparenting | Keep parent changes out of generic patches. | A separately designed move operation preserving related geometry, text, spans and scope. |
| Changing line primary keys | Keep excluded. | No ordinary workflow identified. |
| Arbitrary page file-size bookkeeping | Continue deriving size from actual files. | A verified administrative repair use case. |
| 24 literal CRUD PUT variants | Do not add wrappers merely for verb parity; PATCH alternatives exist. | A concrete need for distinct full-replacement semantics. |
| Relaxing merge/geometry/duplicate-selection guards | Preserve existing constraints. | Evidence that a legitimate workflow needs a safe, compatible extension. |

## Upstream-dependent watchlist

Recheck these when the server is upgraded or this roadmap is resumed. This is a
manual recheck list, not a scheduled monitor. Absence of a native route may justify
an upstream contribution or a separately scoped client-side feature.

The 2026-09-16 refresh leaves every item on this watchlist. Existing user/group
CRUD is implemented; UP-06 concerns the missing password, reset, invitation and
font-administration workflows. Route/schema absence alone is not proof that an
import endpoint cannot handle a format internally, so the UP-04 limitation keeps
that distinction explicit.

| ID | Desired capability | Current dependency |
|---|---|---|
| UP-01 | Revoke shares; manage group membership/ownership, roles and model sharing rights | Live REST metadata still shows additive sharing and user/group CRUD, without revoke, membership/ownership or role-management mutations. |
| UP-02 | Standalone evaluation and advanced training controls | Native evaluation/configuration contracts distinct from the existing ARC-specific training routes. |
| UP-03 | Delete, promote or restore a checkpoint | Dedicated checkpoint lifecycle support. |
| UP-04 | Restore JSON document archives; IIIF Presentation 3; richer METS layer mapping | Upstream import support or a separately designed conversion/restore feature. Schema absence alone does not prove the existing import endpoint cannot handle a format internally. |
| UP-05 | Durable job submission IDs and reliable import progress/recovery | Stable submission identity plus import-record/control APIs; the current audit found neither. |
| UP-06 | Password/reset/invitation and font administration workflows | Existing user/group CRUD does not cover these missing workflows; requires native administration APIs or separately authorized UI integration. |

## Execution and completion rules for later sessions

1. Read this roadmap, the coverage audit and stability policy. Inspect current
   repository changes and the deployed capabilities before editing.
2. Start with the next Ready item unless the user changes priorities. Keep a stable
   item ID when splitting work, and record dependencies and exclusions.
3. Use statuses **Ready**, **In progress**, **Audit first**, **Deferred**,
   **Upstream required**, **Implemented** and **Released**. Optional/conditional
   rows must have their decision recorded before implementation begins.
4. Preserve existing 1.x names, arguments/defaults, result meanings and safeguards.
   Review intentional schema changes against the compatibility baseline; do not
   regenerate it simply to silence a failure.
5. Run checks appropriate to the changed boundary, exercise the actual MCP surface,
   and use Windows/macOS/Linux verification for affected portability behavior.
   Keep source-backed, fixture-backed and live evidence distinct.
6. Update coverage, catalogue/schema, documentation and skill for implemented
   behavior. Additive changes normally use a minor release; release packaging and
   publication follow [RELEASING.md](docs/RELEASING.md) and the requested task scope.
7. Mark Released only after publication and artifact verification. Record the
   exact commit, version, checks and limitations. Deployment remains a separate
   action; a published package is not an installed service update.
8. Never change research data, running jobs or credentials merely to demonstrate
   coverage. Reuse valid session authorization; otherwise keep live checks read-only
   and use isolated fixtures or explicitly authorized disposable data.

## Progress ledger

| Date | Item | Result | Evidence / next action |
|---|---|---|---|
| 2026-09-16 | Baseline | Roadmap saved; no implementation started | API-COVERAGE.md and API-COVERAGE.csv. Next: MCP-01. |
| 2026-09-16 | Post-v1 conditional audit | MCP-01 In progress; MCP-02 Implemented but not Released; MCP-03, MCP-05 and MCP-06 Deferred; MCP-04 Upstream required; UP-01–06 refreshed and retained | Read-only live schema/method probes, pinned-source checks and sanitized decision ledger retained in the private verification record. Live schema capture: 543,492 bytes, SHA-256 `6237decffb416823ef7c16134e4b54573bb13e6e664d35c73c34308c2ff8b454`; MCP-02 focused tests and live identity readback passed; no live writes. Next: implement only MCP-01 after its page/filter contract is reviewed. |
| 2026-09-16 | 1.1.0 integration | MCP-01 and MCP-02 Implemented; MCP-03, MCP-05 and MCP-06 Deferred; MCP-04 Upstream required | Optional native-page reads preserve omitted-argument behavior; `get_script` adds the only new tool. Reviewed 1.x schema additions, coverage map, public docs and release artifacts are synchronized. Publication remains pending. |
