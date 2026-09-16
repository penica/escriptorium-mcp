# MCP module expansion task list

Saved: 2026-09-16. Baseline: MCP v0.5.0.

Implementation authorized on 2026-09-16. Ontology is complete for the audited API scope and is excluded from this expansion list.

| Priority | Status | Module | What needs adding |
|---|---|---|---|
| 1 | Released (0.6.0) | Tasks and job monitoring | Document task groups, document-level progress, filtering, import status/cancellation, and clearer completion/failure reporting. |
| 2 | Released (0.7.0) | Model management | Rename/update/delete models, manage document associations, download model files and available checkpoints. Listing, uploading and basic inspection already exist. |
| 3 | Released (0.8.0) | Training and evaluation | Expose remaining server-supported training options, connect submissions to task groups, and provide consistent checkpoint/result reporting. |
| 4 | Released (0.9.0) | Transcriptions | Bulk create/update/clear line text, transcription statistics and character counts, character-to-page lookup and layer settings. |
| 5 | Released (0.10.0) | Segmentation | Bulk line operations, line merging, individual region/line retrieval, mask regeneration and automatic reading-order recalculation. Region locking requires newer support. |
| 6 | Released (0.11.0) | Pages and image operations | Rotation, cropping, lookup by page order, bulk page moves and server-side filtering. Basic upload/edit/delete/reorder already exist. |
| 7 | Released (0.12.0) | Imports | IIIF manifests, METS files/URLs, explicit import modes and target transcription layers, plus status and cancellation. |
| 8 | Released (0.13.0) | Exports and downloads | More export options, full-document JSON archives, and listing/retrieving/deleting generated downloads. The downloads API requires the newer release. |
| 9 | Released (0.14.0) | Projects, documents and metadata | Search/filter/sort, document statistics, page-ID lookup, document/page metadata CRUD, project/document tags and remaining editable settings. |
| 10 | Released (0.15.0) | Virtual collections | Collection CRUD, complete membership replacement and recognition/segmentation training across documents. |
| 11 | Released (0.16.0) | Alignment and textual witnesses | Manage owned reference files, diagnose native upload ownership, expose ordinary alignment and forced character alignment. |
| 12 | Released (0.17.0) | Sharing, users and groups | Additive project/document sharing, visible directories and native account/group CRUD with explicit creation limits. |
| 13 | Released (0.18.0) | Fonts and presentation settings | List fonts and configure supported transcription-font preferences. Requires the newer release; font upload itself is an admin-interface operation. |

## Implementation constraints

- Follow the priority order unless the user changes it.
- Verify each module's endpoints and editable fields against the deployed API before implementation.
- The user upgraded the deployment to a development image and resumed work on 2026-09-16. Recheck deployed endpoints; keep optional capability detection for older servers.
- Keep custom ARC training controls separate from the standard eScriptorium API.
- Implement and publish modules sequentially with versioned commits and validation evidence. Live deployment upgrades remain separate.
