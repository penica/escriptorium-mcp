# Optional native-page list reads

## Scope

Public list tools that advertise an optional `pagination` input support two
deliberately different modes:

- Omit `pagination` to keep the original all-results behavior. The MCP follows
  every valid native page and returns the same complete result shape as before.
- Supply `pagination` to request exactly one native collection page. The MCP
  makes one guarded collection-page request and returns that native envelope
  without following `next` or `previous`. Existing metadata, identity or scope
  preflights remain when a tool needs them: for example,
  `list_collection_items` reads collection detail before exactly one native
  `items/?page=N` membership-page request. Those preflights do not retrieve an
  additional collection page.

Use discovery as the authority for which tools currently expose this input. The
shared input is:

```json
{"pagination": {"page": 2, "page_size": 20}}
```

`page` is a strict positive integer and defaults to `1`. `page_size` is optional,
strictly positive and at most `50`. It is sent as the native `paginate_by` query
only where that route supports it. Supplying `page_size` on another route is an
honest error; it never becomes a client-side row limit.

## MCP call examples

Read the second page of documents matching a native name/order filter:

```json
{
  "filters": {"name": "Register", "ordering": ["-updated_at"]},
  "pagination": {"page": 2, "page_size": 20}
}
```

Read the first native page of a collection, whose route does not support native
page sizing:

```json
{"pagination": {"page": 1}}
```

Read one task-report page and apply the local workflow-state filter only to that
page:

```json
{
  "workflow_state": 3,
  "pagination": {"page": 3, "page_size": 10}
}
```

Read one generated-export record page and filter that page by report ID:

```json
{
  "task_report_id": 481,
  "pagination": {"page": 2, "page_size": 10}
}
```

`search` on users/groups, `workflow_state` or `method` on task reports, and
`task_report_id` on downloads are local filters. With no `pagination`, the MCP
first retrieves the complete authorized collection and then filters it. With a
selected page, it filters only that page. A sparse or empty filtered page does
not establish that the collection has no matching rows elsewhere.

## Response contract

A selected page retains native envelope fields such as `count`, `next`,
`previous`, `results`, and unknown future fields. It also contains:

```json
{
  "pagination": {
    "mode": "native_page",
    "page": 2,
    "page_size": 20,
    "returned_count": 20,
    "native_total": 87,
    "native_total_scope": "collection",
    "filtered_total": null,
    "filtered_total_scope": "not_filtered",
    "has_next": true,
    "has_previous": true,
    "next_page": 3,
    "previous_page": 1,
    "collection_consistency": "snapshot_not_guaranteed"
  }
}
```

`native_total` is the upstream collection count when it is supplied, otherwise it
is `null` and `native_total_scope` is `"unknown"`. It is not a count of locally
filtered rows. After a local filter, `filtered_total` is the number returned from
the source page and `filtered_total_scope` is `"source_page"`; the top-level
`count` becomes `null` so it cannot be mistaken for a global filtered total.

Use `next_page` or `previous_page` in a new MCP call. The MCP validates native
continuations before returning them: they must identify one positive page on the
same configured origin and original collection route, with no duplicate page
parameter, fragment, unrelated query parameter, redirect, loop, or foreign
collection. Do not send the native `next` or `previous` value as a URL.

## Completion and consistency

Native pagination does not create a snapshot. A record can be created, edited or
removed between page requests, and a native total can change with it. Treat a
selected page as a bounded inspection only.

Do not use one-page list reads to establish that an audit, archive, register
download, job summary, submission-tracking search, ontology scan, or recovery
operation is complete. Those internal aggregate workflows keep complete retrieval
and do not accept a caller-selected page as proof of completion.
