# Reference texts and alignment

Module 11 exposes owned textual witnesses, ordinary reference-text alignment and
forced character alignment. These are separate workflows with different effects.

## Tools

| Tool | Effect |
|---|---|
| `list_textual_witnesses` | Read every owned reference-text record. |
| `get_textual_witness` | Inspect owned metadata by primary key. |
| `upload_textual_witness` | Submit a standalone file, then diagnose ownership visibility. |
| `update_textual_witness` | Rename a reference or replace its stored file. |
| `delete_textual_witness` | Delete the owned reference record. |
| `download_textual_witness` | Save the advertised file to a new MCP-host destination. |
| `align_document` | Align a source transcription against a reference and write a named target layer. |
| `force_align_pages` | Replace character graphs in an existing layer using a recognition model. |

Witnesses belong to the account and can be reused across accessible documents.
The native API has no witness sharing, document attachment, content-edit field,
usage history or format-conversion action. Listing follows every page within the
original route, preserving native metadata and response shape.

## Reference files and standalone creation

Names are nonblank and at most 256 characters. Uploads take an existing, nonempty
UTF-8 `.txt` file on the MCP host. Validation preserves the original bytes, BOM
and line endings. Standalone creation/replacement limits the filename to 100
characters. Direct alignment uploads instead derive the witness name from the
filename stem, which must fit 256 characters. Server storage, quota and proxy
limits still apply; the MCP does not invent a native file-size limit.

**The audited standalone creation route has an ownership defect.** Its generic
serializer does not assign the current user as owner, while all subsequent
witness reads filter by owner. A successful creation can therefore leave a record
the creator cannot access. This is pinned-source evidence; live creation was not
attempted, and the exact deployed source revision is unknown.

`upload_textual_witness` requires `acknowledge_unverified_ownership: true` in its
`upload` object, alongside `name` and `file_path`. This flag is not sent upstream.
After one POST, the tool preserves native acceptance and performs at most one
owned-detail read when the response supplies a valid ID. Its result separates:

- `accepted` and `submission`: the successful native response.
- `ownership_readback`: verified, unverified or unavailable, with diagnostic
  reason, validated ID and any returned detail record.

Matching identities and nonempty owner metadata through the owned route establish
current visibility. Missing or contradictory metadata and failed reads do not.
A failed diagnostic read never discards acceptance or causes another POST.
The MCP does not repair ownership, delete uncertain records or create alignment
jobs merely to upload a file. For a normal usable standalone workflow on the
affected backend, use the web interface or an upstream fix.

Ordinary alignment's explicit file-upload mode uses a separate server path that
sets the owner, and necessarily queues alignment. It is not a standalone upload.

Updates accept name and/or replacement file. Omission preserves an existing
field; nulls and empty changes are invalid. Replacement and deletion can affect
queued tasks that read the reference later. Completed transcription layers are
not deleted merely by deleting the witness. Native deletion requests file cleanup
but does not prove secure physical erasure. There is no automatic retry or
rollback after an uncertain mutation.

## Downloading a reference

`download_textual_witness` first reads owned metadata and checks its identity.
It follows only an advertised witness-storage URL on the configured origin,
without credentials, query strings, fragments or ambiguous traversal paths.
Foreign/CDN/signed URLs are refused rather than receiving an API credential.
Redirects are refused by the existing file transport.

The destination and its `.part` sibling must be new and outside the scan-only
Books archive. Failed transfers retain partial files. Successful results report
the path, byte count and SHA-256 after exclusive publication. There is no native
witness checksum or size field to authenticate the file against; the digest
describes the downloaded bytes. Paths refer to the machine running the MCP.

## Ordinary alignment

`align_document(document_id, job, track=false)` selects an active source layer
with `transcription`, an explicit `layer_name`, and exactly one witness:

```json
{
  "transcription": 9,
  "witness": {"kind": "existing", "witness_id": 4},
  "layer_name": "Aligned reference",
  "acknowledge_target_reuse": true,
  "search": {"kind": "beam", "beam_size": 20}
}
```

Use `{"kind":"file","file_path":"/server/path/reference.txt"}` for direct
upload. It sends the native multipart `witness_file` field without a preceding
standalone witness creation.

The target name can reuse an existing layer, including an archived layer hidden
from normal list/detail calls. Consequently `acknowledge_target_reuse: true` is
required even when the caller expects a new layer. This is an explicit tool
input, not a guarantee of new-layer creation or an interactive approval flow.
The MCP trims the target name as the server does and rejects the current source
layer's name; this compensates for a defective native comparison. It cannot lock
concurrent layer creation or discover every archived collision.

| Option | Supported values and behavior |
|---|---|
| `parts` | Omit for all pages, or supply distinct nonempty document-owned IDs. |
| `region_types` | Omit for all enabled regions plus `Undefined` and `Orphan`, or supply a nonempty distinct subset. |
| `n_gram` | Integer 2–25; default 25. |
| `gap` | Integer 1–1,000,000; default 600. |
| `threshold` | Finite number 0–1; default 0.8. Zero is preserved. |
| `search` | Beam mode with size 1–100, or offset mode with offset 0–80. |
| `merge` | Default false; controls copying unmatched source lines. |
| `add_hyphens` | Default false. |
| `full_doc` | Default true; matching input can span the whole source document. |

Beam mode sends `max_offset=0`; offset mode sends `beam_size=0`. Both native
fields are explicit, avoiding the backend's omitted-beam default overriding a
requested offset search. Required native form defaults are always supplied.

Selected output pages and matching input have different scopes. With
`full_doc=true`, the aligner can read the entire source layer even when only some
output pages are selected. With false it matches each selected page separately.
Region filtering controls matching input. With `merge=true`, unmatched lines
outside the chosen region types can still copy their source text.

Matched lines create or replace target text. With `merge=false`, old unmatched
text in an existing target remains unchanged; it is not automatically blanked.
The operation does not replace segmentation geometry. Do not assume it creates a
complete revision history or a recoverable rollback snapshot.

The native action creates a task group and may create an uploaded witness before
queueing fails. Its success response supplies no witness, group, report or output
layer ID. Acceptance is not completion. External Passim/Seriatim availability,
quota and suitable input remain server concerns; an exposed route does not prove
the executable is installed or that alignment quality will be acceptable.

## Forced character alignment

`force_align_pages(document_id, job)` accepts `model`, `transcription` and an
optional nonempty set of page IDs. The MCP checks the readable recognition model
and selected page/document identities. Model type metadata cannot prove that the
binary architecture supports forced alignment.

The native action accepts archived layers and validates layer membership within
the document before queueing. The MCP therefore does not use the narrower
active-only layer detail endpoint as a preflight. Foreign or inaccessible layers
remain native errors. There is no target layer, witness or search-mode setting.

The task reads existing text and line images/geometry, then **replaces character
graphs in place**. It does not rewrite text, baselines or masks, create a layer or
promise updated average-confidence summaries/revisions. Device and worker
settings are controlled by the backend.

The server queues per-page jobs without a task group. A failure partway through
submission can leave earlier jobs queued; execution can partially update graphs.
The MCP submits once and does not retry. The backend may independently retry
tasks according to its Celery policy, so this is not an exactly-once guarantee.

## Monitoring and cancellation

Use `list_tasks` with exact methods `core.tasks.align` or
`core.tasks.forced_align` and the relevant document. Native serialized reports
do not establish model/witness/output-layer attribution.

Optional `track=true` on ordinary alignment compares groups before and after the
single submission. New matching or temporarily unnamed groups are candidates,
including when there is only one. Failed monitoring preserves acceptance and
must not prompt a resubmission. Forced alignment has no group tracking option.

No dedicated REST alignment-cancel action exists. Existing page/document/task
cancellation has wider effects and upstream limitations; it is not a precise
alignment rollback or guaranteed interruption. In particular, the pinned
alignment cancellation implementation appears to use an invalid report lookup.
That suspected upstream defect was not tested by canceling live work.

## Evidence and limits

Contracts use read-only development-API probes and pinned upstream commit
[`5f17889fe571d8fa25feb5deebec4221d9485d32`](https://gitlab.com/scripta/escriptorium/-/tree/5f17889fe571d8fa25feb5deebec4221d9485d32):

- [Routes, owned witnesses and layer visibility](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py).
- [Witness and alignment serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py).
- [Layer and witness model behavior](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/models.py).
- [Alignment execution](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/tasks.py).

Successful mutations and job submissions are verified through isolated fixtures
and real MCP transports. No live reference upload, alignment, cancellation,
research-text modification or service deployment is part of release testing.
