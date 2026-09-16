# Model management API audit

Audited on 2026-09-16 against the deployed ARC API with GET/OPTIONS only and the upstream master/v26.07 source. Module 2 is implemented for MCP 0.7.0 as described below. Release validation and publication status are recorded separately in [IMPLEMENTATION-STATUS.md](../IMPLEMENTATION-STATUS.md).

## Supported operations

| Operation | MCP tool | Contract |
|---|---|---|
| List/filter | `list_models` | `GET models/`, paginated; `documents=<document ID>`, `job=1` or `job=2` |
| Read | `get_model` | `GET models/{id}/` |
| Upload | `upload_model` | Multipart `POST models/`; numeric MCP job input becomes the required display label |
| Rename/metadata | `update_model` | `PATCH models/{id}/`; writable `name`, `job`, `file_size` |
| Replace model file | `replace_model_file` | Multipart `PATCH models/{id}/`, field `file`, calculated `file_size` |
| Delete | `delete_model` | `DELETE models/{id}/` |
| Stop training | `cancel_model_training` | Existing `POST models/{id}/cancel_training/` |
| Checkpoint listing | `list_model_versions` | Read `versions` on the model; preserve revision IDs and additional metrics |
| File download | `download_model` | Download the advertised current file or checkpoint selected by revision |
| Document associations | `get_model_documents` | Read-only `documents`; processing/training creates associations |

## Serialization details

- Model names permit up to 256 characters.
- Job filters use numeric values **1 = segmentation, 2 = recognition**. POST/PATCH use display labels **`Segment` / `Recognize`**. The serializer's `DisplayChoiceField` accepts labels even though OPTIONS advertises numeric choices. Preserve the MCP's existing numeric input interface and translate at the request boundary.
- `owner`, `training`, `versions`, `documents`, `accuracy_percent`, `rights`, `script`, `parent` and `can_share` are read-only. Sending these fields in PATCH can be silently ignored.
- Current files are returned as media URLs. A checkpoint's `versions[].data.file` is storage-relative, for example `models/abc123/region_epoch=06.ckpt`; `revision` identifies the version. Version data also contains available training epoch/accuracy fields.
- An advertised current file or checkpoint can be absent. Live reads encountered a missing current model file and checkpoints removed during active training even though their historical versions remained advertised. A freshly listed checkpoint was successfully downloaded through MCP with its byte count and SHA-256 verified. HTTP errors must remain errors, with no completed download file reported. Refresh the version list after a missing checkpoint; do not assume a historical artifact still exists.

## API limits and mutation scope

There is no standalone REST association bind/unbind endpoint in either audited source version. The session-authenticated UI has an unbind route, but it is not part of this API-token integration. A `documents` PATCH must not be presented as a working association edit. Likewise, no REST checkpoint revert/delete action was found.

The model API queryset grants readable public/shared models and does not show the UI's owner-only mutation guard. New MCP metadata, file-replacement and deletion operations verify `rights == "owner"` before mutation; reads and downloads use the server's ordinary readable-model permissions. This is a client-side guard, not a fix to upstream authorization.

File replacement, deletion and job/size metadata changes additionally require `training == false`; absent/unknown training state fails this check. Rename-only updates can proceed while training runs. Empty changes, explicit nulls and unsupported association fields are rejected before writes. These preflight reads are not atomic locks: pause concurrent training starts/writers when performing restricted edits.

Replacement updates the current file reference and byte-size metadata without creating a checkpoint backup. Deletion can remove server-managed model files/relationships but does not delete document transcriptions. Changing job metadata does not convert the underlying weights.

## Transfer and adapter behavior

The multipart adapter honors the validated HTTP method, including PATCH for file replacement. Uploads and metadata writes serialize the public numeric jobs as display labels, while listing filters retain numeric values.

Model downloads reuse the authenticated export transfer worker's same-origin, redirect-refusal, exclusive-output, byte-count and SHA-256 protections. Both the final destination and its `.part` path must be new, and model files cannot be placed in the scan-only Books archive. A successful response reports completion only after transfer. HTTP errors such as a missing advertised file remain errors, without a final completed output; interrupted transfers may retain a partial file for inspection.

Only server-advertised files are accepted. Current-file URLs must have the configured scheme/host/port and contain no embedded credentials, query or fragment. Current paths reject traversal, backslashes, nested percent encoding and control characters. Checkpoint resolution requires exactly one matching revision, a storage-relative `models/` path and an unambiguous `/models/` prefix in the current model URL. Unsafe or ambiguous paths fail before transfer. An advertised current URL is required to determine this media prefix even when downloading a checkpoint.

## Sources

- [Model API viewset](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/views.py)
- [Model serializer](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py)
- [DisplayChoiceField](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/fields.py)
- [Model storage and ownership](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/models.py)
- [Session-authenticated UI operations](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/views.py)
