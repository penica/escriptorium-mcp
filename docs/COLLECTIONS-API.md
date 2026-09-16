# Virtual collections

Module 10 adds eight tools for native virtual collections and training from pages
in multiple documents. Collections contain references to existing pages and
transcription layers; they do not copy research content.

## Available operations

| Tool | Operation |
|---|---|
| `list_collections` | Read all collections owned by the authenticated account. |
| `get_collection` | Read one owned collection's metadata. |
| `create_collection` | Create a named collection, optionally with defaults and members. |
| `update_collection` | Edit metadata and optionally replace the complete membership. |
| `delete_collection` | Delete the collection and its membership links. |
| `list_collection_items` | Read every current page/layer membership record. |
| `train_collection_recognizer` | Queue recognition training from saved page/layer pairs. |
| `train_collection_segmenter` | Queue segmentation training from the saved pages. |

Native collections are owner-only, including for staff through this API queryset.
Source pages can come from documents the account may read through ownership or
sharing. The collection API has no sharing, owner transfer, arbitrary search,
sorting, item-by-item mutation, reordering or independent evaluation action.
Unsupported fields are rejected instead of silently ignored.

Collection metadata uses `id`, not `pk`, and includes name, owner, update time and
the default-layer map. Item records include their own ID, document/page/layer IDs,
display names, page order and thumbnail metadata. Responses preserve native extra
fields; thumbnail references do not trigger image downloads. Missing fields are
not fabricated.

Collection lists and item lists follow every page. Pagination stays within the
original collection endpoint and origin, rejects redirects and loops, and
preserves native counts and extra fields. A completed envelope has `next: null`;
a bare list remains a list. A missing or forbidden endpoint is an error, not an
empty collection. The API does not expose a configurable page-size option here.

## Membership and default layers

Creation uses a `data` object, for example:

```json
{
  "name": "Training selection",
  "default_transcriptions": {"4": 9, "8": 15},
  "items": [
    {"document_id": 4, "page_id": 12, "transcription_id": 9},
    {"document_id": 8, "page_id": 31, "transcription_id": 15}
  ]
}
```

Names are nonblank and at most 512 characters. Names need not be unique. Each
page may appear only once, even if a caller supplies different document/layer
contexts for it. IDs must be positive integers. The MCP verifies each source
document, page and layer before sending one mutation. A layer must belong to the
page's document. `document_id` is checking context; the native item payload
contains only `document_part` and `transcription_layer` IDs.

`default_transcriptions` maps decimal document-ID strings to layer IDs. These are
editor selection defaults. They do **not** change existing members' layers or
replace the explicit page/layer pairs used for training. Supplied references are
checked rather than accepted as arbitrary JSON settings.

Updates use `changes`:

- Omit `items` to retain all current membership.
- Supply `items` to replace the complete selection, removing omitted members and
  updating selected layers for retained pages.
- Supply `items: []` to clear membership.
- Omit `default_transcriptions` to preserve the map; `{}` clears it.
- Omitted name stays unchanged. Empty changes and explicit nulls are invalid.

There is no hidden read/append/replace helper that could silently overwrite
another client's selection. Native item ordering is not a promise to retain the
order of the supplied list. Changes to references do not alter source page text,
geometry or ownership.

The native serializer can save collection metadata before modifying membership;
creation can save a collection before creating its links. Failures can therefore
leave partial changes. The MCP sends one mutation and does not retry uncertain
writes. Re-read the collection and items before deciding what to do next.
Preflight checks are observations, not locks or transactions.

Scoped layer reads can hide archived layers. The MCP does not bypass access or
unarchive them. A layer explicitly returned by the scoped API can be used; a
hidden/missing layer causes preflight to fail, even where a native write path
would accept its ID.

## Training and model handling

Both training tools take `collection_id` and `job`, containing `model` and/or
`model_name`, plus optional `override` (default false). They do not accept parts,
one global transcription layer, epochs, batch size, device, learning rate or
other unsupported hyperparameters.

| Input | Native result |
|---|---|
| New `model_name`, no model | Create a new owned model of the requested kind. |
| Existing model, override false | Clone the base into an owned training model; an optional name controls the clone name. |
| Existing model, override true | Train the existing owned model; a supplied name does not rename it. |

The selected model's identity and job kind must match. Overwriting always requires
ownership and stopped training, even when `model_name` is also supplied. Model
names support 256 characters. Omit unused model/name fields instead of null.

The MCP reads every current member and rechecks access to source documents,
pages and layers before submission. Empty collections are rejected. Segmentation
requires at least two distinct pages because the native split reserves a
validation page; a single page would leave no training pages. These checks cannot
freeze the dataset or guarantee useful ground truth, resources or convergence.

Recognition uses nonempty text from each member's saved layer. Segmentation uses
page geometry, with equal type names across documents treated alike; its required
layer membership is not used as a geometry label source. Direction/line-offset
settings can derive from the first eligible document, so mixed conventions need
deliberate dataset selection. Remaining training configuration is server-managed.

The native response contains a confirmed target model ID, for example:

```json
{"status": "training queued", "model_id": 42}
```

This is queue acceptance, not successful training. The server can create a group
and model before queueing fails. The MCP preserves the raw response and makes no
second POST to repair monitoring. Errors or timeouts can leave partial records or
queued work; inspect before retrying.

D-FINE segmentation fine-tuning is rejected during native task execution. Some
training failure paths delete the target model, including when overwriting.
Download needed model files/checkpoints before using a destructive training
option; the MCP cannot promise upstream preservation or restore a deleted model.

## Monitoring and deletion limits

Use the returned model ID with `get_training_report`, `list_model_versions` and
`download_model`. Without a document/group argument, the training report reads
model metrics and checkpoints; an idle model alone is not proof of success, and
advertised files may be missing. Do not label generic scores as CER/WER without
knowing the server's metric.

Collection task groups are stored internally but have no routed collection API
in the audited version. Public task reports omit their collection/model/group
links. `list_tasks` can filter the current user's reports by exact method
`core.tasks.train_from_collection` or `core.tasks.segtrain_from_collection`, but
cannot reliably attribute those reports to one collection or submission.
No group ID or linkage is invented from timestamps or names.

`cancel_model_training` uses the selected model's native cancellation action; it
is not a collection-wide cancellation guarantee. No separate collection cancel
or evaluation tool is available.

**Membership is read when training executes.** Editing after submission can
change the training dataset. Deleting a collection preserves source pages,
documents, layers and models but removes its membership and collection-linked
group history; report links can become null. It does not cancel queued training
and can cause that training to fail. These effects differ from deleting a source
document or model.

## Evidence

Contracts use read-only GET/OPTIONS against the development deployment and pinned
upstream commit
[`5f17889fe571d8fa25feb5deebec4221d9485d32`](https://gitlab.com/scripta/escriptorium/-/tree/5f17889fe571d8fa25feb5deebec4221d9485d32):

- [Collection routes and actions](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py).
- [Membership and training serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py).
- [Collection models and relationships](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/models.py).
- [Collection training execution](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/tasks.py).

The exact deployed commit is unverified. Live probes found an available, empty
collection list and absent collection task-group routes. Training OPTIONS returns
ordinary collection fields, so it is not a reliable training-input schema.
Successful mutations and training submissions are checked with isolated fixtures
through real MCP transports, not against live research data.
