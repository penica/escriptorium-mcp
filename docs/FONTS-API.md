# Fonts and presentation API

Module 13, MCP 0.18.0. Audited against the development API on 2026-09-16
and upstream commit `5f17889fe571d8fa25feb5deebec4221d9485d32`.
The deployed commit is unknown; runtime capability checks govern assignments.

## Catalogue tools

| Tool | Native route | Result |
|---|---|---|
| `list_fonts()` | `GET fonts/` | Complete paginated native metadata. |
| `get_font(font_id)` | `GET fonts/{id}/` | One record with matching positive ID. |

The catalogue is instance-wide for authenticated users. Native ordering is by
name; this view has no declared search, ordering or page-size query options.
All pages are followed within the original collection route and origin.
Unsafe pagination, redirects and loops fail. An unavailable route remains an
error rather than becoming an empty catalogue.

Records preserve `pk`, `name`, `url`, `size_adjust`, `ascent_override`,
`descent_override`, `line_height`, `input_height`, `input_padding_top`,
`input_padding_bottom`, `input_margin_top`, `input_margin_bottom` and
`input_vertical_align`, including unknown future fields. Nulls, zeroes and
negative margins are meaningful metadata and are preserved.

The URL is metadata only. Neither tool fetches font files, forwards credentials
to the advertised URL, installs a font or verifies glyph rendering. Storage may
use a separate host or access policy.

## Set or clear an override

Use existing record tools. Examples below use illustrative IDs and names;
discover actual projects, scripts and font IDs before writing.

```json
{"name":"Archive","settings":{"transcription_font":3}}
```

The preceding arguments call `create_project`. A document can select the same
font through `create_document`:

```json
{"data":{"name":"Register","project":"archive","main_script":"Latin","transcription_font":3}}
```

For existing records, call `update_project` or `update_document`:

```json
{"project_id":1,"changes":{"transcription_font":3}}
```

```json
{"document_id":1,"changes":{"transcription_font":null}}
```

A positive integer selects a font. Explicit null clears the stored override.
Omission preserves the existing setting or native creation default and adds no
font requests to older calls. Other existing settings retain their behavior.

Before sending the field, including null, the MCP checks OPTIONS on the exact
record route. Creation requires a writable field in POST metadata. Updates use
PATCH metadata when present, otherwise native DRF's PUT metadata. A missing,
read-only or unavailable field prevents the write. Font catalogue availability
alone does not prove a serializer supports assignment. Non-null selections also
read the font detail and verify its ID. The server still enforces write access.

Font-bearing mutations make one request attempt; errors are preserved and there
is no automatic retry or follow-up write. A lost response can leave the change
applied. Read the record before deciding whether to repeat it. Capability and
identity preflights do not lock records against concurrent changes.

## Effective font and effects

The server resolves the displayed font in this order:

1. Document override.
2. Project override.
3. Requesting user's preferred font.
4. Editor default when none is set.

`transcription_font` is a direct ID or null. Document reads preserve the native
`effective_transcription_font` object or null; older-server omission stays omitted.
The MCP does not reconstruct this value from incomplete metadata. User fallback
means different callers can receive different effective fonts.

Changing a project font affects documents that inherit it. Clearing a document
override allows project/user fallback and does not force the editor default.
Clearing a project override preserves explicit document choices. These operations
change presentation only, not Unicode text, OCR models, segmentation, scan pixels
or character graphs.

## Native limits

The REST font view is read-only. Font upload, replacement, deletion, family
renaming and metric editing require the eScriptorium admin interface. Supported
admin file formats are TTF, OTF, WOFF and WOFF2; the MCP does not expose upload.

The web user profile supports `preferred_transcription_font`, but the audited
REST user serializer omits it. No account-font setter/getter is advertised here.
Use the native web profile for this setting. General document presentation fields
such as reading direction, line offset, script and confidence display remain in
the existing document tools.

Live checks are read-only. The audited instance had an empty font catalogue;
populated metadata, assignment, inheritance and error behavior are verified with
isolated native-contract fixtures. Successful assignment is not visual
verification of a font's glyph coverage. Installing an MCP release does not
upgrade eScriptorium or its running service.

## Sources

- [Font view and pagination](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py).
- [Font, project, document and user serializers](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py).
- [Font metrics and effective-font resolution](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/core/models.py).
- [Web profile preferences](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/users/forms.py).
