# Stable public contract for 1.x

Version 1.0 established 175 public tools. Version 1.1 adds `get_script` and
optional bounded pagination on supported list tools without changing their
unbounded default. The reviewed machine contract is in
[`contracts/v1-tools.json`](../contracts/v1-tools.json); the complete discovery
catalogue, including descriptions, is in [`tool-schema.json`](../tool-schema.json).
Both STDIO and Streamable HTTP expose the same tools.

## What stays compatible

Within 1.x, existing tool names, documented argument meanings, required inputs,
defaults, omission-versus-null behavior, validation constraints and operation
scope remain compatible. Existing clients must not need new required arguments.
Safety annotations remain accurate: a read operation cannot silently become a
write. An idempotency hint does not guarantee that retrying a failed network
request is safe; follow each tool's retry guidance.

Successful structured tool results retain the `{ "result": ... }` envelope.
MCP-owned report fields and their documented meanings remain compatible. For
example, task summaries preserve their authenticated-user scope, report counts,
terminal percentage and completion/failure flags. A queued submission is not
completion, terminal percentage includes failed/canceled jobs, and an empty
report set is not successful completion. The feature guides and behavior tests
cover these semantics beyond discovery schemas.

New tools, optional arguments and additive response fields may arrive in minor
releases. Fixes without new features use patch releases. Removing a tool, adding
required inputs, narrowing accepted documented inputs or changing existing
result meanings requires a major release. Necessary security corrections must
explain any compatibility impact and migration in the release notes.

## What depends on eScriptorium

All tools currently advertise a general JSON `result`, not a closed model
of every upstream field. Native eScriptorium response fields, available actions,
permissions and task visibility depend on the connected server version and
account. Version 1.0 does not freeze the upstream API or promise newer features
on older servers. Clients must tolerate additional native fields and handle
unsupported operations and permission errors.

Missing fields, explicit null values and numeric zero are distinct. Unknown
arguments are not a supported extension mechanism: some existing tools reject
them and others use the SDK's default handling. Supply only advertised inputs.
Human-readable descriptions and error wording may improve without a major
release; do not parse their prose as machine status codes.

## Reviewing a contract change

`uv run pytest tests/test_stable_contract.py` discovers the actual server without
credentials or API calls and compares existing tools with the independently
checked-in baseline. It guards names, input/output schemas and safety hints.
Schema titles, descriptions, examples and comments are excluded; property names
and literal defaults are retained. Additional tools do not fail this check.

The check intentionally flags any machine-schema change, including compatible
additions. It is a review gate, not an automatic semantic-versioning decision.
For an intentional change:

1. Compare the discovery schema with the baseline and classify the change under
   this policy. Check existing callers and the affected behavior tests.
2. Add regression coverage for changed behavior and document its compatibility
   and server-version requirements.
3. Update only the reviewed baseline entries, adding new stable tools as needed.
   Never regenerate the baseline merely to silence a failing check.
4. Run the contract check and relevant behavior tests before publication.

This schema check does not prove live upstream behavior, authorization correctness,
job completion or installation compatibility. Those require their separate
integration, live-workflow and platform checks.
