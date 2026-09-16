# Live API coverage for 1.1.0

Audited 2026-09-16 against the configured development API, using authenticated
GET and OPTIONS only. No documents, jobs, credentials or service settings were
changed. Historical compatibility baseline: **1.0.0**, commit
`65afe4e6f1cf918399534f641f741c18383d10f3`, **175 tools**. Current release:
**1.1.0**, **176 tools**.

## Result

There is no large untouched functional module in the advertised REST API.
There are small endpoint gaps, deliberate field restrictions and upstream
limitations. The MCP does **not** have literal method-and-field parity with every
REST operation.

The freshly retrieved OpenAPI schema has **107 paths and 213 operations**
(GET/POST/PUT/PATCH/DELETE, excluding OPTIONS/HEAD). Its response SHA-256 is
`6237decffb416823ef7c16134e4b54573bb13e6e664d35c73c34308c2ff8b454`, identical
to the schema retrieved before the module expansion. No newly advertised routes
were found after the 1.0.0 release.

[API-COVERAGE.csv](API-COVERAGE.csv) maps all 213 operations to a primary MCP tool
or an explicit exception:

| Classification | Operations | Meaning |
|---|---:|---|
| Covered route | 179 | A corresponding tool invokes this route and method; this is not a claim that every raw field/value is exposed. |
| PATCH alternative | 24 | The API also advertises CRUD PUT; the MCP exposes partial updates through PATCH. Literal replacement semantics are not exposed. |
| Not exposed | 10 | The exact operations listed below. |

These counts describe route/method coverage, not an overall feature-completeness
percentage. The source also exposes media downloads and action options that the
generated schema does not describe accurately. Existing download tools and the
feature guides cover those separately.

## Exact endpoint gaps

All paths below are relative to `/api/`.

| Capability | Unexposed operation(s) | Current alternative | Recommendation |
|---|---|---|---|
| Document-level training cancellation | `POST documents/{id}/cancel_training/` | `cancel_model_training(model_id)` targets a specific model. | Optional shortcut. Inspected source selects the last currently training model associated with the document; it is not an unambiguous cancel-all action. Prefer model-specific cancellation. |
| API token issuance/rotation | `POST token-auth/` | Existing API key is configured outside tools. | Keep in credential setup/admin tooling unless explicitly needed. Native authentication accepts username/password; source additionally handles `regenerate`. This is the eScriptorium API token, not the MCP HTTP bearer token. |
| Task-report creation | `POST tasks/` | Real job submission tools create work and server reports. | Keep excluded from normal workflows: inserting a report is not submitting work. |
| Task-report editing/deletion | `PUT`, `PATCH`, `DELETE tasks/{id}/` | Read/status tools and dedicated cancellation actions. | Administrative history manipulation, not job control. Do not use report edits to pretend a task succeeded or stopped. |
| Task-group creation | `POST documents/{document_pk}/task_groups/` | Processing submissions create their own groups. | Do not add just for parity: live collection OPTIONS marks every exposed group field read-only. Successful useful creation is unverified. |
| Task-group editing/deletion | `PUT`, `PATCH`, `DELETE documents/{document_pk}/task_groups/{id}/` | Group list/detail/status tools. | Inherited administrative CRUD; no exposed writable group settings. Deletion is not a cancellation API. |

Live confirmation: script detail GET returned 200; OPTIONS confirmed task list/detail
write verbs, the document training-cancel action and token authentication. Group
collection OPTIONS returned 200 with all fields read-only. No missing-operation
write was attempted. Advertised verbs are not proof that a meaningful write will
succeed; permissions, serializers and model constraints still apply.

## Missing raw options and deliberate restrictions

| Area | Raw API capability not directly offered | Current behavior / assessment |
|---|---|---|
| Pagination | Caller-selected `page` and, on applicable lists, `paginate_by`. | Supported list tools expose optional bounded reads while preserving complete retrieval by default. `page_size` is available only on verified routes; see `PAGINATION.md`. |
| Project ontology | Writable `Project.ontology_config` JSON through generic project create/update. | Live OPTIONS confirms it is writable. MCP project input models omit it; native YAML import/export/delete already manage the template. Prefer the dedicated ontology workflow over a raw JSON bypass. |
| Legacy import recovery | `resume_import` on the plural `documents/{id}/imports/` form action. | Neither import tool exposes resume. Source resumes the latest failed import and has missing/nonfailed-record edge cases. This is a real source-backed option gap, not a new route; add only after a dedicated recovery-contract audit. Modern singular `/import/` has no resume field. |
| Reparenting geometry/annotations | Writable `document_part` on line/region serializers and `part` on annotation serializers. | MCP updates remain scoped to the addressed page and omit changing these parent fields. A safe move workflow would need to account for related regions, text and spans; raw foreign-key reassignment is not recommended. Successful cross-page writes were not tested. |
| Line identity | Native line request schema exposes `pk`. | MCP uses IDs to select existing records, including bulk updates; it does not expose changing a line's primary key. Keep this restriction. |
| File-size bookkeeping | Native page/model update serializers expose size fields. | Page-image replacement derives size from actual bytes. Model metadata has its own guarded options. Arbitrary page size falsification is intentionally unavailable. |
| Create-versus-update convenience | Some editable settings are only available after creation, e.g. layer comments/confidence and extra page metadata. | Existing update tools provide these settings. This is an extra call, not an absent end-to-end capability. |
| Input guardrails | Examples include requiring two lines for merge, rejecting duplicate selections and validating geometry. | Some raw server-accepted inputs are deliberately narrower in MCP. These are not missing endpoint families. See the feature contracts. |

The legacy form also accepts IIIF/METS source options that the old file-import
tool does not expose; these workflows are already available through the modern
`submit_document_import` variants, so they are not additional functional gaps.

## Module map

| Module | Existing coverage | Remaining API coverage issue |
|---|---|---|
| Ontology and annotations | Types, document assignments, native YAML, project templates, components, taxonomies and image/text instances. | Raw project JSON and parent/identity changes above; no missing advertised ontology endpoint. |
| Tasks and job monitoring | Reports, groups, document summaries, filters, status and dedicated cancellation. | Direct history CRUD and the optional document training-cancel shortcut. |
| Models | Metadata/file changes, deletion, document associations, versions and downloads. | No additional checkpoint lifecycle endpoint exists in this schema. |
| Training | Document and collection training, available options and report tracking. | Document cancellation shortcut; advanced configuration/evaluation is an upstream gap. |
| Transcriptions | Layers, single/bulk line text, statistics and character-to-page lookup. | No additional advertised action missing; literal CRUD PUT and pagination are separate. |
| Segmentation | Region/line CRUD, bulk lines, merge, ordering, masks and supported locks. | Raw reparenting/identity changes deliberately omitted. |
| Pages | Upload/read/edit/delete, replacement, rotate/crop, lookup/order/move/filter. | Pagination and some create-time convenience fields. |
| Imports | PDF, XML/ZIP, IIIF, METS file/URL, layer targeting, monitoring and cancellation. | Legacy resume option; modern restore/resume is absent upstream. |
| Exports/downloads | Native formats/options, direct text/JSON, generated-download CRUD/file retrieval. | No additional advertised export/download route missing. |
| Projects/documents/metadata/tags | CRUD, settings, searches/filters, statistics, metadata, tags and script detail. | Raw project ontology JSON. |
| Collections | CRUD, items, complete membership replacement and cross-document training. | Dedicated add/remove-member convenience could wrap existing update; not a missing native endpoint. |
| Alignment/witnesses | Witness CRUD/download, alignment and forced alignment. | No additional advertised action missing. |
| Sharing/users/groups | Visible accounts/groups, supported CRUD and additive sharing. | Revoke/member/role operations are absent upstream. |
| Fonts/presentation | Font reads and supported font preferences. | Font administration/profile operations are absent from the native REST surface. |

Two apparent gaps were checked and ruled out:

- `get_annotation(target, kind)` already calls both image and text **detail**
  endpoints. Separate `get_image_annotation`/`get_text_annotation` tools would
  duplicate it.
- Native task-list filters in the schema/source are document, group and ordering,
  plus pagination. They are already supported. State/method filtering is supplied
  locally by MCP. No native date-range/user/document-part filter was found that
  could simply be exposed as an omitted parameter.

## Features requiring upstream work or a separate client-side feature

These are useful potential enhancements, but are not unwrapped routes in the
current API:

- Revoke a single project/document share, manage group members/ownership or assign
  detailed roles; model sharing-right administration.
- Standalone OCR evaluation and user-selected training epochs, learning rate,
  batch size, device or validation split through the audited training actions.
- Delete/promote/restore an individual model checkpoint through a dedicated route.
- Restore a full JSON document archive, IIIF Presentation 3 import, or select an
  exact destination layer for every METS source layer.
- Durable submission IDs and complete import-record progress/resume/control APIs.
- Password/reset/invitation flows and font upload/administration through the native
  REST catalogue. Token authentication is separately present as noted above.

Client-side conversion, read/modify/write helpers or UI automation could implement
some workflows, but must not be presented as existing native API coverage.

## Suggested next work

1. Optionally a **document training-cancel convenience tool**, clearly documenting
   its target-selection behavior; model-specific cancellation already exists.
2. Audit **legacy import recovery** only if it is a real operational need. Avoid
   promising reliable recovery from the inherited form flag alone.
3. Keep task-history CRUD, arbitrary identity/parent edits and raw ontology JSON
   outside ordinary tools unless an explicit administrative use case requires them.

## Evidence and limits

- Fresh live schema and sanitized GET/OPTIONS metadata are retained privately in
  `live-verification/v1-coverage-schema.json` and `v1-coverage-probes.json`.
- Public MCP evidence: [tool catalogue](../TOOLS.md), [machine schema](../tool-schema.json),
  [stability policy](STABILITY.md), and source files `record_tools.py`, `task_tools.py`,
  `job_tools.py`, `task_monitoring.py`, `instance_tools.py`, `project_models.py`,
  `segmentation_models.py`, `instance_models.py`, `file_models.py` and `import_models.py`.
- Existing source audit is pinned to upstream commit
  `5f17889fe571d8fa25feb5deebec4221d9485d32`:
  [views](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py),
  [serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py),
  [legacy import form](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/imports/forms.py).
- The exact deployed container commit is still unverified. Matching schema bytes
  do not prove identical implementation. Generated action schemas have known body
  and parameter omissions, so this is a route/contract audit, not a destructive
  execution test of all operations or proof of complete field/value parity.
