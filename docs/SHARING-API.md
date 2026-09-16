# Sharing, accounts and groups

Module 12 adds 13 tools covering the native account/group fields and additive
sharing actions exposed by the audited REST API. Permissions remain those of the
authenticated eScriptorium account.

## Account operations

| Tool | Scope |
|---|---|
| `get_current_user` | Read the authenticated account and native capability fields. |
| `list_users` | Read visible users, optionally filtering the complete result locally. |
| `get_user` | Read one visible account by primary key. |
| `create_user` | Staff-only native account-row creation. |
| `update_user` | Edit a visible self/staff-authorized account. |
| `delete_user` | Staff-only account deletion. |

Nonstaff account lists/details expose the caller's own account. Staff may see
other accounts. A visible directory is not a global user-search service for every
caller. Returned fields such as `can_invite` do not substitute for the native
`is_staff` requirement on REST account creation/deletion.

Creation requires username and email. First/last names and `is_active` are
optional. Updates accept those same five fields and require at least one supplied
change. Omission preserves a field, empty first/last names clear it, explicit
false deactivates the account, and nulls are rejected. Username syntax follows
Django's Unicode letters/digits/underscore plus `@`, `.`, `+` and `-`, with a
150-character limit. Display names also support 150 characters, including empty
strings. Emails are bounded nonblank inputs; the native server validates their
syntax and uniqueness.

The native REST serializer permits a nonstaff user to change their own email,
username, display names and active status. Staff can edit other visible accounts.
The MCP does not invent an additional staff-only email restriction. Server
authorization remains authoritative after preflight and can change between calls.

**Account creation is not an onboarding workflow.** The audited serializer has
no password field, password-setting hook, invitation or confirmation-email flow.
An accepted row does not establish usable password login, delivery of an email,
or new-address ownership. These tools neither accept passwords nor send
invitations. Staff status, permissions, groups, quotas, expiry, tokens, retention
settings and preferred fonts are not writable through this serializer.

Self-deactivation or staff self-deletion can prevent subsequent authentication.
Changing a username can affect configured username/password access and future
username-based sharing. The MCP does not rewrite its connection configuration or
perform a speculative follow-up read that converts an accepted change into a
failure. Deletion can cascade through native relationships or fail on protected
ones; success is not a complete external-data erasure report.

The audited user permission class can return 403 to OPTIONS/HEAD even when GET
works. User tools therefore do not require successful OPTIONS as a prerequisite
for supported reads or writes.

## Groups

| Tool | Scope |
|---|---|
| `list_groups` | Read all groups in the caller's membership queryset. |
| `get_group` | Inspect one visible group's native metadata. |
| `create_group` | Submit a name and diagnose creator membership/ownership. |
| `update_group` | Rename a visible group. |
| `delete_group` | Delete a visible group. |

Groups are limited to the caller's memberships, including for staff. The audited
REST path does not require a visible group's owner for name edits/deletion; the
MCP does not add that restriction. Native authorization remains in force. Names
are nonblank, at most 150 characters, and subject to server uniqueness checks.
Only the name is writable. Nested users and owner fields are read-only.

Deleting a group can remove access supplied by its sharing/model-right
relationships for every member while retaining source projects/documents. It is
not a tool for removing only one user's membership or one resource grant.

### Native creation limitation

The pinned generic REST create path does not add the creator as a member or set
the separate group-owner relationship. The web form performs both operations.
Consequently a native REST creation can succeed while leaving the new group
inaccessible to its creator. This is source evidence, not a live creation test;
the deployed revision may differ.

`create_group` requires both `name` and
`acknowledge_native_create_limitations: true`. Only the name is sent upstream.
The tool reads the current account, sends one POST, and attempts one bounded
group-detail read when a valid ID is returned. The result preserves:

- `accepted` and `submission`: successful native acceptance and its raw response.
- `verification`: verified, incomplete or unavailable, with observed readability,
  creator membership and creator ownership separately represented.

A matching readable record with explicit creator membership and ownership is
verified. Missing fields remain unknown rather than becoming false. An explicit
different/null owner or empty membership gives negative evidence. Failed reads,
malformed metadata or mismatched identities do not erase acceptance or cause
another creation. Verification describes the observed state, not an atomic
guarantee against later changes.

The MCP does not repair membership/ownership, submit web forms, use admin
endpoints or delete an uncertain new group. Use the native web workflow or an
upstream fix when usable group creation is required on the affected backend.

## Directory filtering

`list_users` and `list_groups` accept optional `search`. They first retrieve all
visible pages through strict same-origin, same-route pagination, then perform
case-insensitive substring matching locally. User matching covers username,
first/last name and email; group matching covers name. No unsupported server
search parameter is sent, and filtering cannot reveal hidden accounts/groups.

Without search, native list/envelope shapes and unknown fields are preserved.
With search, the result is an envelope containing matched raw rows and a local
count, with no next/previous page. Missing/null searchable fields do not become
fabricated empty names. Redirects, loops and unsafe next-page links are refused.

## Additive resource sharing

`share_project(project_id, target)` and
`share_document(document_id, target)` accept exactly one target:

```json
{"kind": "user", "username": "researcher"}
```

```json
{"kind": "group", "group_id": 7}
```

These map to the native `user` or `group` field. They add a grant and preserve
existing assignments. Repeating an identical native grant does not duplicate
the relationship, but the MCP does not automatically repeat failed mutations.
Successful responses retain the native updated resource, including share arrays.

The MCP checks the source record identity and, for a group target, current group
visibility. It does not require a username to appear in `list_users`, because
nonstaff directory visibility is narrower than native username sharing. Native
case-insensitive lookup, ambiguity and validation errors remain server results;
the MCP does not select another account or guess a substitute.

The audited resource querysets/permissions govern sharing; an owner-only rule is
not added. Sharing expands access. Project-level access can apply across its
documents, while direct document grants are only one possible access source.
Existing `get_project` and `get_document` return direct share metadata; these
arrays are not a complete calculation of effective permissions.

## Unsupported operations and failure semantics

The audited API has no revoke/replace-sharing action, role level, expiry,
membership add/remove/leave action, group-owner transfer, password lifecycle,
invitation endpoint or privilege-assignment field. Project/document sharing
arrays are read-only in ordinary PATCH serializers. Sending such fields can be
silently ignored upstream, so unsupported mutation inputs are rejected by the
MCP rather than advertised as successful operations.

All writes use one request attempt. A server error or timeout may leave the
mutation applied; inspect the native state before considering another write.
Preflight checks are observations, not locks or transactions. Creation readback
is a bounded diagnosis of a known native defect; ordinary edits/deletes do not
perform unnecessary after-reads.

## Evidence

Contracts use read-only development-API probes and pinned upstream commit
[`5f17889fe571d8fa25feb5deebec4221d9485d32`](https://gitlab.com/scripta/escriptorium/-/tree/5f17889fe571d8fa25feb5deebec4221d9485d32):

- [User/group querysets and share actions](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/views.py).
- [Writable fields and read-only relationships](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/serializers.py).
- [API permissions](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/api/permissions.py).
- [Web group creation](https://gitlab.com/scripta/escriptorium/-/blob/5f17889fe571d8fa25feb5deebec4221d9485d32/app/apps/users/forms.py).

The exact deployed commit is unverified. Live checks do not create accounts or
orphan groups, change emails/status/sharing, delete users/groups, send messages
or rotate credentials. Successful mutations are tested with isolated fixtures
through actual MCP transports, not against live research accounts.
