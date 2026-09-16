# Projects, documents, metadata and tags

Module 9 extends the existing record tools and adds scoped metadata/tag management
and document statistics. Operations use the authenticated account's native API
permissions. Successful reads do not guarantee write permission. Preflight checks
verify current identities and references; they do not lock concurrent edits.

## Finding records and preserving metadata

`list_projects` and `list_documents` accept optional `filters`. Both support
case-insensitive `name` substring matching, a native `tags` expression, and an
`ordering` list. Documents also accept a numeric project ID in `project`.

| Collection | Ordering fields, optionally prefixed by `-` |
|---|---|
| Projects | `created_at`, `documents_count`, `id`, `name`, `owner`, `updated_at` |
| Documents | `name`, `parts_count`, `updated_at` |

Tag expressions use `none` for untagged records, `1,2` for both tags, and `1|2`
for either tag. `none|1` includes untagged records or records with tag 1. Mixed
separators, empty terms and `none` in a comma expression are invalid. Native OR
queries can return duplicate records; the MCP preserves server rows and counts.

Lists follow pagination. Project records use `id`; documents use `pk`. Existing
no-argument calls and detail tool names remain available. Reads now preserve
native fields, expanded sharing/tag objects, nulls, zeroes, timestamps and unknown
fields. The old connector's synthetic defaults and timestamp rewriting are no
longer applied. A completed collection has `next: null`; a bare upstream list
remains a list. Missing fields on older servers remain missing.

### Optional bounded pages

`list_projects`, `list_documents` and page/record list tools that advertise the
same optional `pagination` input can instead return one native page. Omit
`pagination` to retain the established exhaustive read and its exact existing
shape. Supply it only when one page is the requested scope:

```json
{
  "filters": {"name": "Register", "ordering": ["-updated_at"]},
  "pagination": {"page": 2, "page_size": 20}
}
```

`page` is a positive integer and defaults to `1`; `page_size` is a positive
integer through `50`. It maps directly to native `paginate_by` only for routes
that support it. A route without that native option rejects a supplied
`page_size`; the MCP never silently truncates a complete result locally.

The selected-page response preserves the native envelope and extra fields, then
adds a `pagination` object with `mode: "native_page"`, requested `page` and
`page_size`, `returned_count`, native collection total/scope, `has_next`,
`has_previous`, validated `next_page`/`previous_page`, and
`collection_consistency: "snapshot_not_guaranteed"`. Use the numeric page fields
for another request. Native continuation links are checked for the same route and
valid page number before they are exposed; they are not arbitrary URLs to follow.

The native total is a collection count, not a transaction snapshot. A collection
can change between page requests, so an empty final-looking page does not prove a
stable collection was completely observed. Complete record work remains complete
by omitting `pagination`: `list_document_page_ids`, document/audit reads and job
summaries do not treat a selected page as their whole scope.

## Creating and editing records

Project and document names support the native 512-character limit. Other named
objects retain their own limits. `create_project(name, settings)` keeps the
existing name-only call; optional settings provide `guidelines` and personal tag
IDs. `update_project` edits name, guidelines and tag assignments. Guidelines may
be a URL, an empty string or null. `rename_project` remains available.

Document creation/editing supports name, project **slug**, script **name**, reading
direction, line offset, confidence visualization and document-tag IDs. The project
filter uses an ID, whereas document creation/movement uses a slug. Explicit false
confidence values are retained. Omitted fields are not sent as synthetic defaults.

Writing-system lookup is deliberately distinct from document creation. Use
`list_scripts` for the catalogue or read one known script by its positive primary
key:

```json
{"script_id": 7}
```

`get_script` is read-only and returns the native script mapping unchanged, such as
its `id`, `name`, `iso_code`, `text_direction` and any server-added fields. Feed
the returned **name**, not the numeric ID, to `create_document`:

```json
{
  "data": {
    "name": "Baptisms 1838-1879",
    "project": "druzina",
    "main_script": "Latin"
  }
}
```

Assignments replace the complete tag array: `[]` clears it. Project tags belong
to the caller; document tags must belong to the effective destination project.
The MCP checks this relationship because the native document serializer accepts
tags from other writable projects. When moving a document with tags omitted,
eScriptorium retains its existing assignments. Supply the intended complete tag
array or `[]` when a move should also change those assignments.

A project move changes organization and inherited access/presentation settings.
It does not copy the document. Deleting a document deletes its pages and related
content. **Deleting a project also deletes its documents and cascading content.**
Neither delete operation is merely a folder removal or an archival action.

Font assignment is handled by the later presentation module. Ontology and sharing
have their own tools; arbitrary serializer fields are not accepted here.

## Statistics and page lookup

- `get_document_statistics` returns native region/line typology counts and
  image/text annotation taxonomy counts. These are not character counts or job
  progress. Null types and zero values are preserved. Optional ordering accepts
  `frequency`, `typology`, or `taxonomy`, with an optional `-` prefix. The default
  query can use a one-hour server cache; explicit `refresh: true` recomputes the
  result and, without ordering, rewrites that cache without changing content.
- `list_document_page_ids` returns the native ordered integer list, including an
  empty list. IDs are distinct from page order numbers.
- `find_pages_by_type` accepts `category` (`regions`, `lines`, `text`, `image`)
  and `type_id` (a positive ID or `"none"`). It returns per-page frequencies, not
  individual geometry/annotation records. Native geometry results use
  `document_part_id`; annotation results use `part_id`. Both are preserved.

Transcription character statistics and character-to-page lookup retain their
separate transcription tools.

## Metadata associations and global keys

Metadata tools accept one of these target forms:

```json
{"scope": "document", "document_id": 4}
```

```json
{"scope": "page", "document_id": 4, "page_id": 12}
```

`list_metadata`, `get_metadata`, `create_metadata`, `update_metadata` and
`delete_metadata` operate on association rows in that scope. Creation takes
`{"key":{"name":"Source"},"value":"Archive reference"}`. Key names are nonblank
and at most 128 characters; values are nonblank and at most 512. Optional
`cidoc_id` is at most eight characters and may be blank or null. Repeated creation
can create duplicate association rows; it is not an upsert.

Ordinary `update_metadata` edits the value only. Deleting an association removes
that row, preserving the global key, other associations and the document/page.

**`update_shared_metadata_key` edits a global definition.** Its name or CIDOC
changes can affect other documents and pages using that key. It does not rebind
only the selected row. No native API enumerates all references, so the MCP cannot
promise a complete impact preview. The tool accepts only key changes and sends a
nested-key PATCH, separately from value edits. This avoids the native combined
PATCH behavior that saves a value before a later key update can fail.

Creating a key with an existing name but conflicting CIDOC information can fail
upstream. Renaming into another key's unique name can also fail. No automatic
merge, retry or transactional guarantee is provided. To rebind only one
association, explicitly create the intended association and then delete the old
one, accounting for the fact that those are separate operations.

## Tag definitions

The five tools `list_tags`, `get_tag`, `create_tag`, `update_tag` and `delete_tag`
use either `{"scope":"personal_projects"}` for the caller's project tags or
`{"scope":"project_documents","project_id":1}` for one project's document tags.

Names are nonblank and at most 100 characters. Optional color is nonblank and at
most seven characters; the native field does not require hexadecimal syntax.
Omit color during creation to use the server's generated default. Definition
updates affect all records assigned that tag. Deleting a definition removes its
assignments everywhere in that scope while preserving projects/documents.

To unassign a tag from one record, edit that record's complete tag array. Deleting
the tag definition is a different, wider operation. Native conflicts and access
errors remain errors; the MCP does not invent replacement names or ownership.

## Evidence and limits

Contracts were checked against authenticated GET/OPTIONS on the development
deployment and pinned upstream commit
[`5f17889fe571d8fa25feb5deebec4221d9485d32`](https://gitlab.com/scripta/escriptorium/-/tree/5f17889fe571d8fa25feb5deebec4221d9485d32).
Relevant sources:

- [API views](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py): record filters, statistics, page lookup and scoped metadata/tag routes.
- [API serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py): writable fields, expanded representations and global metadata-key update behavior.
- [Core models](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/models.py): limits, relationships and deletion cascades.

The deployed source commit is unverified. Live probes establish available routes
and metadata, not successful mutation behavior. Mutation checks use isolated
fixtures through the actual MCP transports; no live research records are created,
edited or deleted during release verification. API availability and permissions
can differ on older installations.
