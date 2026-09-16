# Segmentation API contract

Audited on 2026-09-16 against the development API and upstream source. The exact
deployed commit was not exposed; the moving `develop` branch is supporting
contract evidence, not proof of the deployment's source revision. Generated
OpenAPI/OPTIONS action serializers can be inaccurate, particularly for bulk PUT.

## Tools and endpoints

Routes below are relative to `documents/{document_id}/parts/{page_id}/`.
Existing line/region create, patch, delete and explicit reorder tools remain.

| Tool | Method and suffix | Request |
|---|---|---|
| `get_line` | GET `lines/{element_id}/` | `target` identifies document/page/line |
| `get_region` | GET `blocks/{element_id}/` | `target` identifies document/page/region |
| `bulk_create_lines` | POST `lines/bulk_create/` | `{lines:[new line fields]}` |
| `bulk_update_lines` | PUT `lines/bulk_update/` | `{lines:[{pk,...changed fields}]}` |
| `bulk_delete_lines` | POST `lines/bulk_delete/` | `{lines:[IDs]}` |
| `merge_lines` | POST `lines/merge/` | `{lines:[IDs]}` |
| `regenerate_line_masks` | POST `reset_masks/` | Empty body; optional `only=ID,ID` query |
| `recalculate_line_order` | POST `recalculate_ordering/` | Empty body |

The MCP returns native response data. Bulk create/update/delete return a status
and line array. Merge returns status and a `lines` object with `created` and
`deleted`. Mask submission returns `status: ok` with no task ID. Reading-order
recalculation returns `status: done` and the page's line IDs/orders.

## Inputs and scope

Coordinates are finite, nonnegative image-pixel pairs. Baselines require at least
two points; line masks and region polygons require three. A new or changed line
must retain at least a baseline or a mask. Omitted patch fields are unchanged;
explicit null clears only nullable fields. Line `order` is a nonnegative index.
External IDs allow null/blank and at most 128 characters. Region order is read-only
and has no new write argument.

Bulk creation accepts optional nested transcription records with a document-owned
layer, text, character graphs and confidence. Caller-supplied nested line IDs are
forbidden: the server assigns each new line. The MCP supplies the correct
`document_part` from the selected page. Bulk updates expose line fields, not page
moves or nested text edits; use the transcription tools to edit existing text.

Before writes, the MCP verifies page membership and selected line IDs, checks
region references against the page, layer references against the document and
typologies against the document's assigned types. Collections can be bare arrays
or paginated envelopes. Duplicate and unknown selections are rejected instead of
allowing the server to silently process only a matching subset. These are
preflight observations, not atomic locks against other writers.

## Mutation and completion semantics

- Native bulk creation is atomic for lines and their nested transcriptions in the
  audited development implementation.
- Bulk update validates before saving but saves rows sequentially without an
  endpoint transaction. A later save failure can leave earlier changes applied.
  The MCP sends one PUT and never retries a write automatically. Re-read affected
  records after an error or timeout before deciding what to submit next.
- Bulk deletion removes geometry and attached text/history and other cascading
  relationships. This differs from bulk text clearing. Returned detailed records
  are not guaranteed to contain every deleted relationship or a complete backup.
- Merge requires two to eight distinct lines, each with a baseline. The minimum
  of two is an intentional MCP restriction; upstream accepts a single line.
  The server orders and combines text using geometry and script, not the caller's
  ID order. It creates a replacement and deletes originals atomically. Character
  graphs, confidence and history are not preserved. Region/type selection follows
  server rules. A merged mask is not promised to be a newly computed union; use
  explicit mask regeneration when needed.
- Mask regeneration is asynchronous. Omit `line_ids` for all eligible lines or
  provide a nonempty selection. An empty selection is rejected. The worker uses
  baseline-bearing lines; quota/permission failures propagate. Acceptance is not
  completion and contains no task or group ID to associate automatically.
- Reading-order recalculation is synchronous and uses document direction plus
  page geometry. It can overwrite intentional manual ordering and has no
  per-request reading-direction override.

## Region locking and compatibility

Region create/update support `locked` only when writable field metadata advertises
it. If absent, the MCP reports the feature unavailable instead of letting an older
server silently ignore it. A permission error remains an error. Other region
edits do not require that field to exist. Locking affects editor cutting/overlap
behavior; it is not access control and does not prevent API edits or deletion.

Actual mutation verification uses isolated HTTP fixtures through STDIO and
Streamable HTTP. Live verification uses reads/metadata only. Publishing this
package does not upgrade the user's running service or change eScriptorium data.

## Source evidence

- [API views](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/views.py): nested scope, bulk wrappers, reset masks and recalculation.
- [API serializers](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/serializers.py): line/region fields, bulk partial updates, detailed nested text.
- [Line merger](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/core/merger.py): eight-line maximum, replacement/deletion and text metadata behavior.
- [Core tasks](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/core/tasks.py): asynchronous mask recalculation.
