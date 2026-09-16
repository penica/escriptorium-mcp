---
name: escriptorium
description: Work with eScriptorium through its MCP server to manage documents and ontology, correct transcriptions and segmentation, run OCR or training, export text, and archive complete registers. Use for eScriptorium workflows, not general handwriting transcription without an eScriptorium connection.
---

# eScriptorium

Use the connected `escriptorium` MCP tools. Read their current input schemas instead of reconstructing API requests or assuming optional fields. If the connection is unavailable, report that prerequisite; this skill does not install or authenticate the server.

## Find the right records

- A page is a **document part**. Pass primary keys returned by the tools, never printed page numbers or positions.
- Read projects, documents, pages, transcription layers and models as needed to resolve the user's target. Reuse IDs already established in the conversation when their identity is unambiguous.
- Creating or moving a document uses a project **slug**; choosing its writing system uses a script **name** from `list_scripts`.
- `move_page` uses a **zero-based index**. Line ordering is separate from page ordering.

## Correct text and geometry

Read the relevant page's lines and transcription records before writing corrections. `create_line_transcription` takes a segmented line ID and a layer ID. `update_line_transcription` and `delete_line_transcription` take the **line transcription record ID**, which is different from the line ID.

Geometry is in image pixels: baselines need at least two points and polygons at least three. For PATCH tools, omit fields that should remain unchanged; explicit `null` clears a nullable field. Deleting a segmented line can also remove its transcription text.

Apply changes within the user's authorized scope. Existing authorization carries forward; ask only when the intended target or a destructive replacement falls outside that scope. A read or export request does not authorize editing the source.

## Run OCR, imports and training

- Select explicit page IDs. Models have job type **1 = segmentation**, **2 = recognition**; uploaded model files are Kraken models.
- OCR may replace text in its target layer, and segmentation with override may replace existing geometry. Select the intended layer and override behavior from the user's request.
- Recognition training needs a ground-truth layer and a starting model or new model name. Segmentation training needs at least two distinct segmented pages and a starting model or new name. Keep page IDs distinct; omit unused model/name options instead of null. Selected model kind must match the action. Overwriting a selected model requires ownership and stopped training, even with `model_name`; model preflights are not atomic locks, and the server validates page/layer membership.
- Optional `track: true` preserves submission acceptance and returns candidate groups. Even one candidate is unproven; concurrent jobs and initially missing methods prevent reliable attribution. Unavailable monitoring is not failed acceptance and must not trigger resubmission. Leave tracking off to retain the raw response shape.
- A successful submission means **queued**, not completed. Inspect task reports, model state or page workflow before reporting success. Task states are **0 queued, 1 running, 2 crashed, 3 finished, 4 canceled**.
- Use `list_task_groups` and `get_task_group` to inspect available groups; do not assume a group is linked to a particular model. `get_document_job_status` can filter by group; otherwise it includes historical reports. Task reports belong to the authenticated user, while group buckets can describe a broader set. `terminal_percent` counts finished, crashed and canceled reports; it is not a success rate or page progress. Empty or unknown reports do not prove completion.
- `get_training_report` combines model metrics/checkpoints with optional caller-selected document/group task summaries. A group requires its document ID. Idle state does not prove success, caller-selected groups are not confirmed model links, and advertised checkpoints may be missing. Preserve raw/missing/zero scores; do not label generic validation scores as CER/WER. The audited standard API has no independent evaluation action or hyperparameter request controls.
- `list_tasks` supports document/group/date ordering and local state/exact-method filters. `get_import_status` reads import task history and messages; it cannot provide native import processed/total counts. No visible reports does not prove no import exists.
- Prefer dedicated page, model or `cancel_document_import` actions for their respective jobs. **`cancel_task` has document-wide side effects:** even when given one report ID, the server also marks all document training models and imports canceled. `cancel_document_tasks` explicitly cancels all queued/running document work. The import action targets the latest import, not an arbitrary report. If a submission times out, inspect remote state before retrying: the original write may already have succeeded.

## Manage model files

- Filter `list_models` by document/job and inspect `get_model` before editing. `update_model` accepts name, numeric job or storage-size metadata; omit unchanged fields and do not pass nulls. Changing job metadata does not convert weights.
- Model metadata/file/delete tools require ownership. Job/size edits, `replace_model_file` and `delete_model` require stopped training; renaming can proceed during training. These checks are observations, not locks against concurrent writers.
- Use `list_model_versions` to find a checkpoint's exact revision, then `download_model` with that revision or omit it for current weights. Destination paths belong to the MCP host and must be new, outside the scan-only Books archive. A listed file may be missing; report a download as complete only after receiving its byte count and checksum.
- Replacement does not create a checkpoint backup. When the user's request requires retaining the original, download it before replacement/deletion. Deleting a model does not delete document transcriptions.
- `get_model_documents` reads associations only. The audited REST API cannot bind/unbind models or revert/delete checkpoints. Use the UI for unbinding; do not run processing jobs solely to manipulate associations.

## Export or archive

Use `export_transcriptions` for direct text/JSON output in reading order. Use `request_server_export` for server-generated ALTO/PAGE XML/text archives, then `download_export` with the completed export URL. Submission alone does not provide the finished file; some eScriptorium installations deliver its link through a notification. Do not invent a download URL.

For register acquisition, use `download_register` with the catalogue parish, register ID, English type and catalogue years. It downloads **all available scans** directly beneath the server's configured `ESCRIPTORIUM_BOOKS_ROOT`, including partial files and the manifest. Keep transcription exports outside that Books tree. Destination folders and files must be new; resolve existing conflicts without overwriting them.

Report the resulting path, scan count and manifest or checksum evidence. Keep **download completion**, **visual inspection** and **transcription completion** distinct. Available scans do not prove that the historical register has no missing pages. Follow the user's archive conventions when supplying catalogue metadata.

## Paths and connections

All upload paths, export destinations and archive roots belong to the **machine running the MCP server**. With Streamable HTTP, a path on the client's computer is not automatically available on the server. Windows drive/UNC paths and macOS/Linux mount paths must match the server's operating system and accessible storage.

STDIO is the default for a local client-managed process; Streamable HTTP is the option for a separately running service. Transport choice does not change the eScriptorium tools or make local files remotely accessible. Keep credentials in server configuration, never in tool arguments, generated examples or this skill.

## Ontology and annotation corrections

Use `get_document_ontology` for document-assigned IDs and `audit_document_ontology` to inspect usage, duplicate labels and invalid assignments. Public catalogues can omit private types. Add missing types with `add_document_ontology_type` and use its resulting document-local IDs.

On older servers definitions are shared: global rename/delete tools can affect other documents. For a document-only rename, add a replacement and use `merge_ontology_types`. Repairs and merges preview by default; use `apply=true` within existing authorization after checking the target and scope. Null replacement source means untyped content; null target clears assignments.

Prefer `patch_annotation_taxonomy` for selective schema edits; it reads and preserves omitted settings and relations. `update_annotation_taxonomy` replaces the complete definition: convert nested components to IDs and typology to `{name}`, preserving every display field. Taxonomy `components=[]` clears linked fields and `typology=null` clears its type. Deleting taxonomies, components or annotation types can delete annotations or stored values.

Use instance tools for actual image annotations or text spans. Text spans take segmented line IDs, a transcription layer and zero-based offsets; image coordinates are integer pixels. `as_w3c` is read-only. Instance components are **upserts**: omitted components or `components=[]` preserve existing values, unlike taxonomy component lists. Set one component's value to `null` to clear its content; no endpoint deletes just that component-value relation. Do not delete the shared component definition as a substitute.

`merge_annotation_taxonomies` moves source instances only when the target has the same image/text marker family and supports every stored component. Source deletion is opt-in through `delete_source=true` after a clean rescan.

## Ontology transfer and recovery

Probe `get_ontology_capabilities` before choosing native YAML import/export or project templates. A registered MCP tool does not prove that the connected server supports its endpoint. A 403 is denial; a 404 means absent or hidden, not a certain server version. Native document import can replace definitions and affect annotations; project import sets a template for future documents. Preserve returned import warnings. Native files live on the MCP host and are limited to 16 MiB.

`export_ontology_snapshot` returns versioned JSON **schema only**. Save it as JSON or pass it to `restore_ontology_snapshot`, which previews by default and adds missing definitions. Same-name conflicts stop writes; existing schema is never deleted. Snapshots do not contain annotation instances, text, geometry or content type assignments, so they cannot undo destructive document edits.

Pause other writers during repairs, taxonomy read/merge/write edits, merges and snapshot restoration. These are multiple API calls without atomic conditional writes or a transaction. Inspect status and progress after applying. A timeout or partial failure may leave writes in place; re-read/audit or re-export before retrying. Do not report a preview or partial result as completion.
