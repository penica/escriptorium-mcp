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
2. **Locally verified, publication pending:** Model management (0.7.0), six new tools and filtered model listing; 102 tools total. Contract evidence and API limits are recorded in docs/MODEL-API.md.
3. **Pending:** Modules 3–13 in roadmap order.

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

### 0.7.0 — Model management (locally verified; GitHub CI/publication pending)

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

### Next release

Module 3: training and evaluation, target 0.8.0, after model management is verified and published.
