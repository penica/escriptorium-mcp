# Transcription API contracts

Audited 2026-09-16 against the deployed development API using read-only requests,
and upstream v26.07/develop source. The deployment's exact source commit was not
reported by the API. Mutation behavior is verified with isolated HTTP fixtures
through actual MCP clients; live research transcriptions are not modified.

## Operations

All paths below are relative to `/api/`. `D` is a document PK, `P` a page PK,
`T` a layer PK and `R` a line-transcription record PK. A text-record PK differs
from its segmented-line PK.

| MCP operation | Method and route | Contract |
| --- | --- | --- |
| Bulk create | POST `documents/D/parts/P/transcriptions/bulk_create/` | `{lines: [{line, transcription, content, ...}]}`; returns `{status, lines}`. |
| Bulk update | PUT `documents/D/parts/P/transcriptions/bulk_update/` | `{lines: [{pk, ...changes}]}`; returns an array of saved records. Non-atomic. |
| Bulk clear | POST `documents/D/parts/P/transcriptions/bulk_delete/` | `{lines: [R, ...]}`; 204. Blanks content only. |
| Read text record | GET `documents/D/parts/P/transcriptions/R/` | Raw record including graphs/confidence/history. |
| Read/edit layer | GET/PATCH `documents/D/transcriptions/T/` | Name, archived, nullable comments and average confidence. |
| Statistics | GET `documents/D/transcriptions/T/stats/` | `ordering` is frequency, -frequency, char or -char. Raw line_count/characters response. |
| Character lookup | GET `documents/D/transcriptions/T/parts_by_char/` | Required `char` query; returns parts with IDs, names, filenames and frequency. |
| Filter page text | GET `documents/D/parts/P/transcriptions/` | Optional `transcription=T`; follows pagination. Unfiltered legacy behavior retained. |

## Scope and failure handling

Older bulk handlers look up record IDs globally. The MCP verifies the page,
line/layer membership and every update/clear record ID before sending writes.
Duplicate IDs and line/layer pairs are rejected; reference-changing updates also
check against unchanged records. Pagination is followed during membership checks.
Single-record updates that change line/layer references use the same checks.
Preflight cannot prevent concurrent changes; no transaction or lock is claimed.

Bulk updates save rows sequentially. An error can follow earlier successful saves.
The MCP sends one PUT, preserves a partial-write warning on failure, and does not
retry mutations. Inspect current records before resubmission. Server-normalized
content and raw response shapes are preserved instead of echoing input as success.

Bulk clear retains graphs, confidence, existing history and the text rows. It does
not create a new history revision. Single-record DELETE actually removes the row.
Layer DELETE archives/renames and retains texts; deleting the default manual layer
is protected by the server. Bulk create bypasses single-create progress/author
hooks, so it is not a promise of identical bookkeeping.

## Fields and statistics

Content accepts blank strings up to 2048 characters. Layer names allow 512
characters. Graphs are nullable arrays; each object may include a single character,
a polygon of at least three coordinate pairs, and confidence between zero and one.
Graph properties are optional but not nullable. Average confidence is nullable
numeric metadata; the serializer does not impose the graph confidence range.
Omitted edit fields are preserved and explicit null clears only nullable fields.

Statistics count stored characters, including stored HTML markup, and may be cached
for one hour. They are not normalized plain-text or grapheme counts. Character
lookup uses one Unicode code point. Both statistics and lookup first verify the
layer. A lookup 404 means unavailable or hidden; 403 remains access denial.

## Deployment findings and schema limits

The development deployment supports character lookup, native ontology YAML,
fonts, generated downloads, virtual collections and region locking. Those other
modules retain their own roadmap order. Existing ontology tools detect native
support without implementation changes.

Bulk-update OPTIONS returns 500 even though PUT is exposed (GET returns 405 with
PUT in Allow). Generated OpenAPI metadata omits bulk wrappers and misstates bulk
responses; it also omits the character query argument. Implementation uses the
source-backed contracts above, not generated metadata alone.

## Sources

- [v26.07 API actions](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/views.py): TranscriptionViewSet and LineTranscriptionViewSet.
- [Development API actions](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/views.py): scoped bulk actions, statistics and parts_by_char.
- [Development serializers](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/serializers.py): TranscriptionSerializer and LineTranscriptionSerializer.
- [v26.07 models](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/models.py): layer archival and graphs_schema.

Branch URLs are moving references; source observations and live read-only evidence
were recorded on the audit date. No exact deployment SHA is inferred.
