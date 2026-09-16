# Pages and image operations API contract

Audited on 2026-09-16 using read-only development-server probes and public upstream
commit `5f17889fe571d8fa25feb5deebec4221d9485d32`. Moving-branch and pinned source
files matched at audit time. The deployed container's exact commit is unverified;
live metadata confirms routes/fields, not every mutation implementation detail.

## Tools and endpoints

| Tool | Method and route under `/api/` | Contract |
|---|---|---|
| `list_pages` | GET `documents/{D}/parts/` | Optional name filter and ordering; follows pagination |
| `get_page_by_order` | GET `documents/{D}/parts/byorder/?order={index}` | Zero-based position; one validated redirect to page detail |
| `rotate_page` | POST `documents/{D}/parts/{P}/rotate/` | `{angle}`; positive angle is clockwise |
| `crop_page` | POST `documents/{D}/parts/{P}/crop/` | `{x1,y1,x2,y2}` in current image pixels |
| `bulk_move_pages` | POST `documents/{D}/bulk_move_parts/` | `{parts:[IDs],index}` |
| `replace_page_image` | PATCH `documents/{D}/parts/{P}/` | Multipart image and computed byte size |
| `update_page` | PATCH `documents/{D}/parts/{P}/` | Supplied editable metadata |

Existing image upload, page detail, single-page move and deletion remain. Generated
OPTIONS action metadata uses ordinary page/document serializers, so it does not
accurately describe rotation/crop/bulk-move request bodies.

## Reads, filtering and lookup

`list_pages(document_id)` retains the existing response shape. Optional `filters`
supports `name`, a case-insensitive substring match across page name **or original
filename**, and `ordering`, a list of supported sort fields. Supported fields are
`order`, `name`, `original_filename` and `updated_at`; prefix a field with `-` for
descending order. These are server-side filters. No workflow, tag or date-range
filter is invented. Native extra response fields are retained.

Page order is a position, not the page primary key. Native lookup returns 302 to
the page detail, or sometimes 200 with an error object. The MCP treats the error
object as a failed lookup and permits only one redirect on the same origin to
`documents/{requested document}/parts/{positive page ID}/` within the configured
API prefix. Query/fragment additions, another document, another origin and further
redirects are refused. Pagination also rejects foreign origins, redirects and
loops. Credentials are never forwarded to an arbitrary lookup/pagination target.

## Rotation

The MCP accepts nonzero integer angles from -359 through 359. This intentionally
excludes fractional values and whole-turn/no-op angles: native rotation filename
bookkeeping handles integer suffixes more reliably. Positive angles rotate
clockwise; the output canvas expands to fit the rotated image.

Rotation changes the image path and transforms line baselines/masks, region
polygons and image annotation polygons. It does not transform character graphs in
line transcriptions. Text content and text-annotation offsets remain. The large
thumbnail is regenerated immediately; other thumbnails can be queued. Old image
files may remain and image-size bookkeeping is not refreshed by the native method.

`status: done` reports synchronous image/geometry work, not completion of every
background thumbnail. Filesystem and row updates are not one atomic transaction.
After any error/timeout, inspect the page before retrying; the MCP does not retry
this operation automatically.

## Cropping

Supply integer upper-left `(x1,y1)` and lower-right `(x2,y2)` corners. The MCP checks
positive width/height and current image dimensions before submitting one request.
Padded/out-of-bounds crops are deliberately excluded, although the native image
library can accept them.

**Cropping overwrites the image file in place. Discarded pixels have no native
recovery guarantee.** Line baselines/masks and region polygons are translated by
the crop offset, but they are not clipped or deleted. Geometry outside the crop
can remain negative or outside the new image. Existing MCP geometry inputs require
nonnegative coordinates, so such shapes may need a separately authorized repair.

Native cropping leaves image annotation polygons and character graphs unchanged.
It does not regenerate thumbnails, refresh image-size bookkeeping, rename the
file to invalidate caches or recalculate reading order. The MCP does not silently
add further corrective writes. Image and row changes can partially succeed; a
failure is not proof that the original image is intact. Re-read before retrying.

## Bulk page moves

Public `move.page_ids` becomes native `parts`. The MCP rejects empty/duplicate
selections and verifies every ID belongs to the document before writing, instead
of letting the server silently ignore unmatched IDs. `index` is an insertion
position in the original page order; -1 appends. The MCP allows 0 through the
original page count, plus -1, and rejects other negative/out-of-range values.

Selected pages retain their **current relative order**, regardless of caller ID
order. Example: `[A,B,C,D,E]`, selecting B/D with index 4, becomes `[A,C,B,D,E]`;
index -1 becomes `[A,C,E,B,D]`. The native response is `status: moved`, not an updated
page list. Preflight observations do not lock concurrent moves.

## Metadata, upload and replacement

Editable metadata includes name (maximum 512 characters), source (maximum 1024 characters), comments,
document-assigned typology, original_filename (maximum 1024 characters) and max_avg_confidence.
Name/source/original_filename allow blank but not explicit null. Comments,
typology and max_avg_confidence are nullable. Confidence summary is finite stored
metadata, not a recomputation; the native serializer has no 0–1 restriction.
Omitted fields stay unchanged. Typology assignment is checked against the
requested document's enabled part types.

Original filename edits change metadata, not the stored image path. Order and
other read-only fields use their dedicated actions. Raw image_file_size editing
is not exposed as arbitrary metadata: image replacement supplies the actual
uploaded file's byte count.

`upload_page` can replace an existing image when its original filename matches;
it does not guarantee a new page. Native upload generates a card thumbnail and
queues conversion. `replace_page_image` explicitly targets one existing page and
uses ordinary multipart PATCH. That update does not run upload's create-only
conversion, thumbnail or duplicate-filename hooks. Existing segmentation and text
remain, but coordinates are not resized/reprojected to fit the replacement image.
Host paths refer to the machine running the MCP server.

## Verification and sources

Mutation verification uses isolated source-shaped fixtures through actual MCP
clients. Live checks use GET/OPTIONS only, including the safe lookup redirect.
Publishing a package neither upgrades a running service nor modifies research
images.

- [Views](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py): page filters/actions and document bulk moves.
- [Serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py): move semantics, editable fields and duplicate-filename upload behavior.
- [Models](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/models.py): rotation/crop filesystem, geometry and thumbnail effects.
