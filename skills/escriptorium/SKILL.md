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

## Record settings, metadata and tags

Use project/document filters for name, native tag expressions and supported ordering; document filtering takes a numeric project ID, while creation/movement takes a slug. Raw record reads preserve newer fields, including expanded tags/sharing. `list_document_page_ids` returns ordered IDs; `find_pages_by_type` returns page frequencies for geometry or annotation types. `get_document_statistics` counts geometry/annotations, not characters or job progress; refresh recomputes and, without ordering, rewrites the default cache.

Tag assignments on projects/documents replace the complete array, and `[]` clears it. Document tags must match the effective project. Moving with tags omitted retains existing assignments; explicitly replace or clear them when intended. Definition edits through `update_tag` affect every assignment in that scope. `delete_tag` unassigns the definition everywhere; edit one record's array to remove only one assignment. Deleting a project also deletes its documents and cascading content.

Metadata targets distinguish a document from one of its pages. `update_metadata` edits the association's value; `delete_metadata` removes only the association. Creation is not an upsert and can produce duplicate rows. `update_shared_metadata_key` edits a global key name/CIDOC definition and can affect other documents/pages. Use it only when that wider effect is within the user's request; a single-row correction does not imply a global rename. The API cannot enumerate every affected reference. Do not combine a value correction with key editing or retry an uncertain mutation automatically.

## Pages and images

Use `list_pages` filters for name/original-filename substring search and supported sort fields. `get_page_by_order` takes a zero-based position and returns a page record; use its primary key for subsequent edits. Page-order lookup errors do not mean an empty document.

`bulk_move_pages` takes `move.page_ids` and `move.index`. Every page must belong to the document. Selected pages retain current relative order, regardless of caller ID order. Index refers to the original order; -1 appends. Pause concurrent page moves because preflight is not a lock.

`rotate_page` accepts nonzero integer angles from -359 to 359; positive rotates clockwise. `crop_page` takes in-bounds integer corners. Cropping overwrites discarded pixels and translates line/region geometry without clipping it. It leaves image annotations and character graphs unchanged and does not refresh thumbnails. Rotation transforms image annotations but leaves character graphs unchanged. These operations can partially apply on failure; inspect before retrying, and do not report a queued thumbnail as complete.

`replace_page_image` explicitly targets an existing page, preserving segmentation/text without resizing coordinates or running upload's thumbnail/conversion hooks. Ordinary `upload_page` can replace an existing image with the same original filename. Ensure destructive image changes are within the user's authorized scope; read/export authorization alone does not cover them. Local image paths belong to the MCP host.

Page metadata accepts original filename and stored confidence summary. A filename metadata edit does not rename the actual image file, and changing a summary does not recompute confidence. Use the returned document-assigned typology IDs.

## Correct text and geometry

Read the relevant page's lines and transcription records before writing corrections. `create_line_transcription` takes a segmented line ID and a layer ID. `update_line_transcription` and `delete_line_transcription` take the **line transcription record ID**, which is different from the line ID.

Geometry is in image pixels: baselines need at least two points and polygons at least three. For PATCH tools, omit fields that should remain unchanged; explicit `null` clears a nullable field. Deleting a segmented line can also remove its transcription text.

Use `get_line` / `get_region` for individual geometry records. A line can have a baseline, a mask, or both; changes must leave at least one geometry. External IDs and line order are editable. Region `locked` requires supported writable metadata and is only an editor preference, not a permission lock.

Bulk line creation can include text in document-owned layers. Bulk update uses line PKs and can partially apply on failure; re-read before retrying. Bulk line deletion removes geometry and attached text/history. `merge_lines` requires two to eight distinct lines with baselines and deletes originals; geometry/script determines text order, and graphs/confidence/history are not retained. Returned deleted records are not a complete backup. Pause concurrent writers; membership preflight is not a lock.

`regenerate_line_masks` queues processing for all eligible page lines when `line_ids` is omitted, or a nonempty selection. Acceptance has no task ID and is not completion. `recalculate_line_order` replaces page ordering synchronously and can overwrite deliberate manual ordering. A merged mask is not guaranteed to be recomputed; request regeneration separately when appropriate.

Use `get_line_transcription` to inspect a text record including history. Line text creation/edits accept character graphs and average-confidence metadata. `get_transcription` and `update_transcription` read/edit layer settings; `get_page_transcriptions` optionally filters by `transcription_id`. Layer `delete_transcription` archives/renames while retaining text, and the default manual layer is protected.

Bulk text tools check page/document membership before writing, including paginated records. Supply text-record PKs to bulk update/clear and segmented-line PKs with layer IDs to bulk create. Bulk updates are non-atomic: after any failure, re-read affected records before retrying. Pause concurrent writers; preflight is not a lock. Bulk clear blanks only content, preserving rows, graphs, confidence and old history without creating a revision. Bulk create does not run the single-create progress/author hooks.

`get_transcription_statistics` returns nonempty-line counts and stored-character frequencies; sum frequencies for the stored-character total. Results include stored markup and can be cached for one hour. `find_transcription_pages_by_character` queries one Unicode code point on supported servers. Do not treat these counts as normalized text/grapheme counts, or an unavailable/denied lookup as an empty successful result.

Apply changes within the user's authorized scope. Existing authorization carries forward; ask only when the intended target or a destructive replacement falls outside that scope. A read or export request does not authorize editing the source.

## Run OCR, imports and training

- Prefer `submit_document_import` for explicit sources: `pdf_file`, `xml_file`, `iiif_url`, `mets_file` or `mets_url`. Local files live on the MCP host; eScriptorium fetches remote URLs under its network policy. PDF/IIIF import images only. IIIF supports Presentation 2 image-service manifests, not Presentation 3. XML/ordinary ZIP selects a layer with `name` or `transcription_id`; METS uses `name` or `prefix_transcription_id` as a prefix for separate source layers, not one exact destination layer. Omit unused name/ID fields instead of null. Scoped lookup normally hides archived layers; no implicit unarchive occurs.
- XML matches existing page original filenames and can skip unmatched pages with warnings. `override=false` can still replace text/images. XML override deletes page geometry and its text/history across layers. Use absolute references in uploaded METS XML or a self-contained METS ZIP. Imports are not atomic; errors may leave records or queued jobs. Preserve returned errors/warnings and inspect before retrying. The legacy `import_document_file` retains its original endpoint. JSON document-archive restore and automatic resume are not supported.
- Select explicit page IDs. Models have job type **1 = segmentation**, **2 = recognition**; uploaded model files are Kraken models.
- OCR may replace text in its target layer, and segmentation with override may replace existing geometry. Select the intended layer and override behavior from the user's request.
- Recognition training needs a ground-truth layer and a starting model or new model name. Segmentation training needs at least two distinct segmented pages and a starting model or new name. Keep page IDs distinct; omit unused model/name options instead of null. Selected model kind must match the action. Overwriting a selected model requires ownership and stopped training, even with `model_name`; model preflights are not atomic locks, and the server validates page/layer membership.
- Optional `track: true` preserves submission acceptance and returns candidate groups. Even one candidate is unproven; concurrent jobs and initially missing methods prevent reliable attribution. Unavailable monitoring is not failed acceptance and must not trigger resubmission. Leave tracking off to retain the raw response shape.
- A successful submission means **queued**, not completed. Inspect task reports, model state or page workflow before reporting success. Task states are **0 queued, 1 running, 2 crashed, 3 finished, 4 canceled**.
- Use `list_task_groups` and `get_task_group` to inspect available groups; do not assume a group is linked to a particular model. `get_document_job_status` can filter by group; otherwise it includes historical reports. Task reports belong to the authenticated user, while group buckets can describe a broader set. `terminal_percent` counts finished, crashed and canceled reports; it is not a success rate or page progress. Empty or unknown reports do not prove completion.
- `get_training_report` combines model metrics/checkpoints with optional caller-selected document/group task summaries. A group requires its document ID. Idle state does not prove success, caller-selected groups are not confirmed model links, and advertised checkpoints may be missing. Preserve raw/missing/zero scores; do not label generic validation scores as CER/WER. The audited standard API has no independent evaluation action or hyperparameter request controls.
- `list_tasks` supports document/group/date ordering and local state/exact-method filters. `get_import_status` reads import task history and messages, optionally within a caller-selected `group_id`; it cannot provide native import processed/total counts. Import `track=true` also returns only unconfirmed candidates. No visible reports does not prove no import exists. Check finished reports for skipped-file warnings and separately queued image conversion.
- Prefer dedicated page, model or `cancel_document_import` actions for their respective jobs. **`cancel_task` has document-wide side effects:** even when given one report ID, the server also marks all document training models and imports canceled. `cancel_document_tasks` explicitly cancels all queued/running document work. The import action targets the latest import, not an arbitrary report; it does not roll back pages and may miss queued work before report attachment. If a submission times out, inspect remote state before retrying: the original write may already have succeeded.

## Virtual collections

Use collection tools for reusable page/layer selections spanning documents. A collection uses `id`, while source pages/layers use `pk`. Each member supplies `document_id`, `page_id` and `transcription_id`; every reference must be readable within that document. Updating `items` replaces all members, `[]` clears them and omission preserves them. `default_transcriptions` maps document IDs as strings to layer IDs and does not supply missing training membership. Deleting a collection preserves source pages/text but removes its grouping; it does not cancel queued work.

`train_collection_recognizer` needs at least one page; `train_collection_segmenter` needs two distinct pages. Both accept a starting model and/or name plus override. Overwrite requires an owned idle model; a supplied name does not rename it. Membership is read when the server executes training, so keep selections stable while queued. D-FINE finetuning is unsupported upstream and its failure path can delete the target model, including an overwrite target; do not use this flow for D-FINE.

Acceptance can include a confirmed `model_id`, but no task/group ID. Use `get_training_report` and `list_model_versions` for that model. The audited server has no collection task-group route; do not pass a collection ID as a document ID or invent task attribution. Collection writes and submissions can partially apply; inspect before retrying.

## Manage model files

- Filter `list_models` by document/job and inspect `get_model` before editing. `update_model` accepts name, numeric job or storage-size metadata; omit unchanged fields and do not pass nulls. Changing job metadata does not convert weights.
- Model metadata/file/delete tools require ownership. Job/size edits, `replace_model_file` and `delete_model` require stopped training; renaming can proceed during training. These checks are observations, not locks against concurrent writers.
- Use `list_model_versions` to find a checkpoint's exact revision, then `download_model` with that revision or omit it for current weights. Destination paths belong to the MCP host and must be new, outside the scan-only Books archive. A listed file may be missing; report a download as complete only after receiving its byte count and checksum.
- Replacement does not create a checkpoint backup. When the user's request requires retaining the original, download it before replacement/deletion. Deleting a model does not delete document transcriptions.
- `get_model_documents` reads associations only. The audited REST API cannot bind/unbind models or revert/delete checkpoints. Use the UI for unbinding; do not run processing jobs solely to manipulate associations.

## Export or archive

Use `export_transcriptions` for direct single-layer text/JSON output in reading order. Use `request_server_export` for native ALTO/PAGE XML/text or JSON document archives; OpenITI/TEI require server enablement. Supply an active layer even when selecting all layers. Omit parts/region types for the whole document; explicit subsets remain subsets. Native JSON options include images, character geometry, document metadata, annotations, model metadata, all layers and ZIP/tar.gz.

For a full native document archive, select JSON, omit parts/region types and enable the desired inclusion flags, normally all of them when preservation is requested. `include_models` stores catalogue metadata, not weights; download needed model/checkpoint binaries separately. Native archives can skip missing images, omit database/ontology fields and include archived layers without their archive-status flags. Export ontology YAML separately when required. There is no JSON archive restore. Anonymization changes selected author fields only; it does not remove private names from content, metadata or filenames. Page metadata remains even when document metadata inclusion is off.

On supported servers use `list_downloads`, optionally filtered locally by `task_report_id`, and `get_download` for owned metadata. `download_generated_export` takes a 32-character lowercase hexadecimal fingerprint and a new MCP-host destination, verifies identity/size and returns bytes/SHA-256. It ignores advertised file URLs as routing authority and increments server access counters. Expired metadata can remain visible while file retrieval fails. The checksum proves downloaded bytes, not archive completeness. Existing files and partials are never overwritten, and exports stay outside Books.

Export submission returns no task/group/download ID and creates no group. Inspect `list_tasks` with method `imports.tasks.document_export` and preserve skipped-page warnings. A download's report ID confirms artifact/report linkage, not which client submission caused it. Registration can fail after a successful report; a completion notification may still carry a usable URL for `download_export`. Do not invent URLs or retry simply because no row appeared. `delete_download` removes the owned record and requests file removal, with no guarantee of physical erasure; it leaves source documents intact.

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
