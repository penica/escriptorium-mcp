# Module expansion execution record

## Objective
Implement all 13 modules in MODULE-ROADMAP.md in order, preserving existing tools. Publish each tested module with an appropriate version increment, complete changelog and explanatory GitHub commit. Do not mark the overall objective complete until every module is verified.

## Release policy
- Additive module releases increment the minor version: 0.6.0 for module 1, then 0.7.0 onward.
- Corrections without new features increment the patch version.
- Document changed arguments or behavior explicitly; preserve existing calls where possible.
- Each release updates package/server version, generated tool catalogue/schema, installer references, changelog and this record.
- Validate unit/integration tests, both MCP transports where relevant, lint/types, distribution build, and actual MCP client behavior. Live deployment checks are read-only; mutation tests use isolated fixtures.
- Commit and push only the relevant module and release material. Confirm remote commit and CI status.

## Current work
1. **Released and verified:** Tasks and job monitoring (0.6.0).
2. **Released and verified:** Model management (0.7.0), six new tools and filtered model listing; 102 tools total. Contract evidence and API limits are recorded in docs/MODEL-API.md.
3. **Released and verified:** Training and evaluation (0.8.0), optional tracked submissions and the new `get_training_report`; 103 tools total. API limits are recorded in docs/TRAINING-API.md.
4. **Locally verified, publication pending:** Transcriptions (0.9.0), with a fresh audit of the upgraded development API. Modules 5–13 remain pending in roadmap order.

## Baseline evidence
- Initial public commit: 73f08eb (MCP 0.5.0, 89 tools).
- GitHub compatibility run 35070341311 succeeded across Windows/macOS/Linux and Python 3.11/3.13.
- Local secrets, private runtime evidence and distributions remain ignored.

## Completed module releases
### 0.6.0 — Tasks and job monitoring

- Added seven tools and extended task filtering; 96 tools total. See CHANGELOG.md for complete behavior and compatibility limits.
- Full regression run: 162 passed in 166.49 seconds. The additional authenticated HTTP monitoring test passed separately; the current suite contains 163 tests.
- Ruff, strict Basedpyright (including the release builder), installer shell syntax and skill validation passed.
- Actual MCP STDIO checks against the ARC backend passed for document summaries, groups, group detail, document/group status, import history and queued-state filtering. No live jobs were submitted or canceled.
- Fixture-backed MCP tests cover cancellation request bodies, pagination, plain-list/envelope compatibility, filters, permission/missing-parent errors, empty/unknown/mixed states and failure messages. Both STDIO and authenticated Streamable HTTP were exercised.
- An isolated installation of the wheel advertised 96 tools and returned a fixture-backed summary that correctly distinguished terminal failure from success.
- Wheel, source archive and WSL transfer archive built. Inner/outer SHA-256 checksums and private-file exclusion verified; release builder refuses accidental archive replacement.
- Actual WSL/systemd service deployment is separate and has not been changed.
- Public commit: `7d0cbb3ac44e21570af146ab7bba1a5fa9e70061`.
- [Compatibility run 35079792398](https://github.com/penica/escriptorium-mcp/actions/runs/35079792398) passed all six jobs: Windows/macOS/Linux with Python 3.11/3.13.
- [GitHub release v0.6.0](https://github.com/penica/escriptorium-mcp/releases/tag/v0.6.0) published the wheel, source distribution, WSL archive and checksum; all four assets verified uploaded.
- Fresh installer and 0.5.0-to-0.6.0 upgrade passed in temporary directories, preserving URL/key/token/archive settings, private configuration permissions and command launcher.

### 0.7.0 — Model management

- Implemented metadata edits, file replacement, deletion, checkpoint listing, association reads and current/checkpoint downloads; `list_models` adds document/job filters.
- New model mutations require ownership. Replacement, deletion and job/size edits additionally require an explicitly idle model; rename-only updates remain available during training.
- Preserved numeric public job inputs with corrected API label serialization and multipart PATCH dispatch. Model names support 256 characters.
- Downloads enforce advertised files/revisions, origin/path restrictions, exclusive destinations, byte counts and SHA-256 reporting. Missing advertised files remain errors.
- Document associations are read-only in the audited REST API; no bind/unbind or checkpoint revert/delete tool is claimed.
- Full regression: 211 tests passed in 224.35 seconds. Ruff lint/format, strict Basedpyright for source/tests/scripts and the programming-rule audit passed. Tests exercise both MCP transports, exact upload/PATCH payloads, ownership/training guards, metadata, binary downloads and failure paths.
- Read-only MCP STDIO checks against ARC passed for filtered listing, document associations, checkpoint listing and a 15,296,557-byte checkpoint download with an independently verified SHA-256. Live training rotated an older advertised checkpoint: the missing file correctly failed, and refreshing the advertised versions supplied an available checkpoint. No live models or jobs were modified.
- Updated package/server/installer versions, model contract documentation and bundled skill. Actual STDIO discovery generated the catalogue/schema with 102 tools and verified server version 0.7.0.
- Release builder lint/format/strict types, installer shell syntax and skill validation passed. Built wheel, source distribution and WSL transfer archive; verified its outer hash and 17 inner hashes, normalized ownership metadata and included model/releasing guides. Wheel contains all three new model modules. Source/wheel inspection found no private environment/config files or live evidence.
- Fresh installer and real 0.6.0-to-0.7.0 upgrade passed in temporary directories, including a path with spaces. URL/key/token/Books configuration, private backups, 0600 permissions and linked launcher were preserved. The installed wheel advertised 102 tools and passed actual STDIO metadata updates, association/checkpoint reads, byte/checksum-verified current/checkpoint downloads and invalid-null rejection against isolated fixtures. No service was installed or changed.
- Public commit: `f618cf3fb0c38fa01847ec2c66d66dd5f18e2057`.
- [Compatibility run 35082582284](https://github.com/penica/escriptorium-mcp/actions/runs/35082582284) passed all six jobs: Windows/macOS/Linux with Python 3.11/3.13.
- [GitHub release v0.7.0](https://github.com/penica/escriptorium-mcp/releases/tag/v0.7.0) published all four artifacts. Uploaded asset digests matched the final local wheel, source distribution, WSL archive and checksum.

### 0.8.0 — Training and evaluation

- Added `get_training_report`: raw model metrics, checkpoint records and optional caller-selected document/group training task summaries. Idle state is not success, model/group attribution is not assumed and no CER/WER or independent evaluation is invented.
- Existing training tools add optional `track=false` by default for raw-response compatibility. Tracking compares groups before/after one POST and exposes candidates, including initially null methods, with attribution explicitly unconfirmed. Optional monitoring failure preserves acceptance and never resubmits.
- Selected models must match the training action. Overwrite requires ownership and `training == false`, including requests also containing a model name. Training inputs reject duplicate pages and explicit null model/name options; names support 256 characters. Server submission serializers remain authoritative for document/page/layer membership.
- Standard server-supported training fields are retained. The audited API has no independent evaluation action or hyperparameter request fields; custom ARC and virtual-collection training remain separate contracts.
- Full regression: 253 tests passed in 303.18 seconds. All 42 focused training cases also passed, covering STDIO and authenticated HTTP, both training actions, exact request bodies, input/model guards, unconfirmed attribution, monitoring HTTP/parse failures, single submission and raw report metrics. Ruff lint/format, strict Basedpyright for source/tests/scripts, the programming-rule audit and skill validation passed.
- Read-only MCP STDIO checks against ARC passed for model metrics, preserved checkpoint records and a caller-selected document/group report containing 72 visible task reports. The result explicitly retained caller-supplied attribution. No live training jobs were submitted, canceled or modified.
- Fresh installation and a real 0.7.0-to-0.8.0 upgrade passed in temporary directories, preserving the complete URL/key/token/Books configuration, private backup and 0600 permissions, linked launcher and installed version. The isolated wheel advertised 103 tools and passed raw null/zero-metric reporting and accepted training after a monitoring failure with exactly one fixture POST. No service or live model was changed.
- Package/server/installer metadata, training documentation, roadmap and bundled skill are updated. Actual STDIO discovery generated the catalogue/schema with 103 tools. Wheel, source distribution and WSL archive built; both new training modules are included. Outer and 18 inner hashes, normalized ownership and private-file exclusion passed.

### Next release

Module 4: transcriptions, target 0.9.0, after training and evaluation is verified and published.
- Public commit: `a1aeb813236caca8f8691dc1905b22f52b4f215b`.
- [Compatibility run 35084887534](https://github.com/penica/escriptorium-mcp/actions/runs/35084887534) passed all six Windows/macOS/Linux and Python 3.11/3.13 jobs.
- [GitHub release v0.8.0](https://github.com/penica/escriptorium-mcp/releases/tag/v0.8.0) published all four artifacts after the user resumed work. Each GitHub asset's SHA-256 and size matched the previously verified local distribution.
- Subsequent workflow-only commits updated actions to Node.js 24 and separated caches by Python matrix version. [Run 35087328474](https://github.com/penica/escriptorium-mcp/actions/runs/35087328474) passed all six jobs with zero annotations at `5c54d7eb2c73da73f50db5e9b0920c247da3ece3`.

### 0.9.0 — Transcriptions (locally verified; GitHub CI/publication pending)

- Added eight tools for bulk create/update/clear, individual text/layer reads, layer settings, statistics and character lookup; 111 tools total. Existing page-text reads gain optional layer filtering; single text operations gain graphs/confidence and scoped reference edits.
- Added page/document membership preflight, pagination, duplicate IDs/pairs and collision rejection. Bulk update uses native PUT with partial-write errors and no retry. Bulk clear preserves rows/history/graphs/confidence. Layer deletion documentation now matches archival semantics.
- The upgraded development API was audited read-only. Character lookup, native ontology YAML, fonts, downloads, collections and region locking are available. Exact deployed source SHA is unknown; generated OpenAPI bulk metadata is inaccurate, so contracts use source and observed endpoint metadata.
- Initial regression failures confirmed missing tools before implementation. New tests drive actual STDIO and authenticated HTTP, including foreign-reference rejection, one-PUT partial failure, 204 clearing, nullable fields, Unicode and layer archival.
- Full regression: 319 tests passed in 398.22 seconds. Ruff lint/format, strict Basedpyright for source/tests/scripts, programming-rule checks, installer syntax and skill validation passed. GitHub CI/publication remain pending.
- Focused module verification: all 66 transcription tests passed in 105.91 seconds. Structured MCP results preserve empty, single-item and multi-item arrays; test decoding was corrected to read the complete result instead of the first text block.
- Read-only local MCP STDIO against the development backend verified 111 tools/version 0.9.0, layer/detail reads, 99 page/layer-filtered records, 188 nonempty lines, 70 stored-character entries and matching character lookup frequencies. Existing model training-report reads also passed. No live writes were performed.
- Package QA passed with 19 inner checksums, the outer checksum, normalized archive ownership, private-file exclusion and all new text modules in the wheel. Fresh 0.9 installation and an actual 0.8-to-0.9 upgrade in temporary paths with spaces preserved URL/key/token/Books settings, 0600 configuration/backup permissions and the command launcher. No systemd service was touched.
- The isolated installed interpreter (`-I`) discovered version 0.9.0 and 111 tools, returned both records from a bulk update, preserved zero statistics/lookup values and cleared text without deleting rows/history against isolated fixtures. Final artifacts are rebuilt after this ledger update before publication.
