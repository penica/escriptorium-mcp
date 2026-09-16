# MCP module expansion task list

Saved: 2026-09-16. Baseline: MCP v0.5.0.

Implementation authorized on 2026-09-16. Ontology is complete for the audited API scope and is excluded from this expansion list.

| Priority | Status | Module | What needs adding |
|---|---|---|---|
| 1 | Released (0.6.0) | Tasks and job monitoring | Document task groups, document-level progress, filtering, import status/cancellation, and clearer completion/failure reporting. |
| 2 | Released (0.7.0) | Model management | Rename/update/delete models, manage document associations, download model files and available checkpoints. Listing, uploading and basic inspection already exist. |
| 3 | Implemented (0.8.0), release validation | Training and evaluation | Expose remaining server-supported training options, connect submissions to task groups, and provide consistent checkpoint/result reporting. |
| 4 | Pending | Transcriptions | Bulk create/update/delete line text, transcription statistics and character counts. Character-to-page lookup requires newer eScriptorium. |
| 5 | Pending | Segmentation | Bulk line operations, line merging, individual region/line retrieval, mask regeneration and automatic reading-order recalculation. Region locking requires newer support. |
| 6 | Pending | Pages and image operations | Rotation, cropping, lookup by page order, bulk page moves and server-side filtering. Basic upload/edit/delete/reorder already exist. |
| 7 | Pending | Imports | IIIF manifests, METS files/URLs, explicit import modes and target transcription layers, plus status and cancellation. |
| 8 | Pending | Exports and downloads | More export options, full-document JSON archives, and listing/retrieving/deleting generated downloads. The downloads API requires the newer release. |
| 9 | Pending | Projects, documents and metadata | Search/filter/sort, document statistics, page-ID lookup, document/page metadata CRUD, project/document tags and remaining editable settings. |
| 10 | Pending | Virtual collections | Collection CRUD, membership management and training from collections spanning multiple documents. Currently absent. |
| 11 | Pending | Alignment and textual witnesses | Manage reference texts; expose alignment and forced-alignment actions. Currently absent. |
| 12 | Pending | Sharing, users and groups | Project/document sharing, user/group discovery and permitted account/group operations. Currently absent. |
| 13 | Pending | Fonts and presentation settings | List fonts and configure supported transcription-font preferences. Requires the newer release; font upload itself is an admin-interface operation. |

## Implementation constraints

- Follow the priority order unless the user changes it.
- Verify each module's endpoints and editable fields against the deployed API before implementation.
- Most expansion does not require the development branch. Use stable v26.07 for newer features and detect optional capabilities at runtime.
- Keep custom ARC training controls separate from the standard eScriptorium API.
- Implement and publish modules sequentially with versioned commits and validation evidence. Live deployment upgrades remain separate.
