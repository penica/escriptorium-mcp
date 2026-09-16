# Ontology and annotation API coverage

Version 0.5.0 exposes 89 MCP tools overall. This map covers the ontology and annotation surface implemented by the adapter, including newer server endpoints that may be unavailable on a particular installation. Paths below are relative to `/api/`; `d`, `p` and `id` are database primary keys. `kind` is `block` (region), `line`, `part` (page) or `annotations` for type definitions; annotation instance `kind` is `image` or `text`.

## Route and method map

| API route | Method | MCP tool / behavior |
|---|---|---|
| `types/{kind}/` | GET | `list_ontology_types`; follows pagination; public/template catalogue may omit private document types |
| `types/{kind}/` | POST | `create_ontology_type`; create/reuse a named definition, without attaching it |
| `types/{kind}/` | OPTIONS | Internal capability check; `get_ontology_capabilities` reports metadata; color writes require a writable color field |
| `types/{kind}/{id}/` | GET | `get_ontology_type`; private document types may return 404 |
| `types/{kind}/{id}/` | PATCH | `update_ontology_type`; name and optional supported color; `update_ontology_type_color` changes only color |
| `types/{kind}/{id}/` | DELETE | `delete_ontology_type`; shared definitions affect other documents; annotation type deletion may cascade |
| `documents/{d}/` | GET | `get_document_ontology`; assigned types with actual document-local IDs |
| `documents/{d}/modify_ontology/` | PATCH | `set_document_ontology`; supplied category lists replace membership, omitted categories stay unchanged |
| `documents/{d}/parts/`, `parts/{p}/blocks/`, `parts/{p}/lines/` under the document | GET | Inventories used by `audit_document_ontology`, `replace_ontology_assignments` and `merge_ontology_types` |
| `documents/{d}/parts/{p}/`, its `blocks/{id}/` or `lines/{id}/` | PATCH | Repair tools patch `typology` only; ordinary page/region/line edit tools also expose these records |
| `documents/{d}/taxonomies/components/` | GET / POST | `list_annotation_components` / `create_annotation_component` |
| `documents/{d}/taxonomies/components/{id}/` | GET / PATCH / DELETE | `get_annotation_component` / `update_annotation_component` / `delete_annotation_component` |
| `documents/{d}/taxonomies/annotations/` | GET / POST | `list_annotation_taxonomies` (optional image/text target filter) / `create_annotation_taxonomy` |
| `documents/{d}/taxonomies/annotations/{id}/` | GET | `get_annotation_taxonomy` |
| `documents/{d}/taxonomies/annotations/{id}/` | PATCH | `update_annotation_taxonomy` sends a complete replacement definition; `patch_annotation_taxonomy` first reads and merges supplied changes |
| `documents/{d}/taxonomies/annotations/{id}/` | DELETE | `delete_annotation_taxonomy`; annotation instances may cascade; optional final step of `merge_annotation_taxonomies` |
| `documents/{d}/parts/{p}/annotations/{kind}/` | GET | `list_annotations`; paginated; text optionally filters by `transcription` |
| `documents/{d}/parts/{p}/annotations/image/` | POST | `create_image_annotation`; taxonomy, integer pixel coordinates, optional values/comments; part comes from the addressed page |
| `documents/{d}/parts/{p}/annotations/text/` | POST | `create_text_annotation`; taxonomy, layer, line IDs, zero-based offsets, optional values/comments |
| `documents/{d}/parts/{p}/annotations/{kind}/{id}/` | GET / DELETE | `get_annotation` / `delete_annotation` |
| `documents/{d}/parts/{p}/annotations/image/{id}/` | PATCH | `update_image_annotation`; supplied scalar/geometry fields and component upserts |
| `documents/{d}/parts/{p}/annotations/text/{id}/` | PATCH | `update_text_annotation`; supplied span/layer fields and component upserts |
| `{documents|projects}/{id}/ontology/export/` | OPTIONS / GET | Capability probe / `export_native_ontology`; native YAML bytes saved to a new host file |
| `{documents|projects}/{id}/ontology/import/` | OPTIONS / POST | Capability probe / `import_native_ontology`; multipart `file`, native YAML or server-supported legacy JSON |
| `projects/{id}/ontology/` | OPTIONS / GET / DELETE | Capability probe / `get_project_ontology` / `delete_project_ontology`; future-document template |

The MCP uses PATCH for edits rather than exposing redundant PUT variants. It exposes no arbitrary raw API request tool. Ordinary API permissions still govern all operations.

## Composed workflows

- **Add a document type:** `add_document_ontology_type` reads current membership, creates/reuses the type, attaches it through `modify_ontology`, and re-reads IDs. Creation and attachment are separate writes.
- **Repair assignments:** `replace_ontology_assignments` previews by default. Null source selects untyped content; null target clears classification. `merge_ontology_types` additionally removes source membership only after usage checks; it does not globally delete the source definition.
- **Merge annotation taxonomies:** `merge_annotation_taxonomies` inventories both annotation kinds across all pages, requires a compatible image/text marker family and every stored component on the target, then changes taxonomy IDs while verifying other values remain. `delete_source` defaults to false. Optional deletion requires a clean source rescan.
- **Portable snapshots:** `export_ontology_snapshot` returns JSON with `format: escriptorium-ontology`, `version: 1`, `scope: schema-only`. It includes assigned page/region/line type names and colors, components and allowed values, and taxonomy display settings and named relations. IDs are resolved at the destination. Duplicate names and unresolved references are rejected.
- **Additive restoration:** `restore_ontology_snapshot` previews by default. It creates missing definitions in dependency order and leaves existing schema in place. Conflicting same-name definitions or unsupported required colors block writes. It excludes annotation instances, transcription text, geometry, content type assignments, project templates and unrelated global catalogue entries. It is not a full document backup or destructive rollback mechanism.

The MCP uses PATCH for updates, including complete field replacements; separate PUT wrappers would expose the same editable fields. HEAD and routine OPTIONS are protocol metadata, not additional content operations. Read-only IDs, generated W3C and internal ordering fields are not editable ontology inputs.

## Write semantics that differ

| Input | Meaning |
|---|---|
| Document allowed-type category omitted | Preserve that category |
| Document allowed-type category `[]` | Clear membership in that category; newer servers may also clear content assignments |
| `patch_annotation_taxonomy` field omitted | Read and preserve the existing setting/relation |
| `update_annotation_taxonomy` display field omitted | Reset to the model default; this tool requires the complete intended definition |
| Taxonomy `components=[]` | Remove linked schema fields |
| Taxonomy `typology=null` | Clear its annotation type |
| Instance `components` omitted or `[]` | Preserve all existing component values; the adapter sends the empty list required by the upstream serializer |
| Instance component `{component: id, value: null}` | Clear that value's content while retaining its component relation |
| Instance component with nonempty string value | Create/update that component's value; other components remain |
| Nullable colors/display fields/comments set to `null` | Explicitly clear the field where supported; omission preserves partial-update fields |
| Instance `comments=[]` | Explicitly replace comments with an empty list |
| Annotation `as_w3c` | Server-generated read-only representation; not accepted as a write payload |

There is **no upstream endpoint to delete one annotation's component-value relation**. Clearing its content is supported. Deleting a component definition is a broader operation that can remove values across annotations; it is not a substitute for deleting one relation.

## Version and permission gates

`get_ontology_capabilities` first reads the requested document/project, then probes OPTIONS on its native routes and type collections. A missing or denied parent remains an HTTP error. Endpoint evidence distinguishes `available`, `denied`, `unavailable_or_hidden` and `unknown`, and reports allowed methods and serializer fields where supplied. HTTP 404 does not establish a server version; private resources can also be hidden. A project export may return 404 when no template is set even if the route exists.

Native import/export requires the expected GET/POST method. Unavailable or denied native file actions return capability evidence with `changed: false` before any transfer/write. Project template actions and color writes also check capabilities before proceeding. The tools remain discoverable on older servers, but report unsupported capabilities instead of fabricating support. Public templates may be read-only even on newer servers.

Native transfers use host paths, refuse redirects and overwrites, and cap import/export at 16 MiB. Preserve import warnings returned by the server. Document import can replace schema and affect existing annotations. Project import sets a template for future documents; deleting that template does not alter existing documents. Use portable snapshots when native file routes are unavailable.

## Concurrent writers and partial failures

Pause other writers for read/merge/write taxonomy edits, repairs, merges and snapshot restoration. The upstream API offers no transaction or atomic conditional-write guarantee for these composed workflows. Preflight checks and re-reads can detect changes but cannot close the final race before a write or deletion.

Inspect each result's status and progress fields (`changed`, `stopped_at`, `source_removed`, `changed_routes`, `source_deleted`, or `completed`, depending on the tool). Partial writes are retained; no rollback is attempted. After a failure or timeout, re-read/audit or export a fresh snapshot before deciding whether to retry. Do not report completion from a preview or a partially successful result.

## Contract references

The route map is implemented in the adapter's ontology, annotation, instance, taxonomy and snapshot modules. Upstream semantics are defined by eScriptorium's [API views](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/views.py), [serializers](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/serializers.py) and [API routes](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/urls.py). These development-branch references describe evolving capabilities; use runtime probes and the installed server's responses to determine availability.
