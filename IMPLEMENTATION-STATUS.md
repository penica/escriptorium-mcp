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
1. **Implemented and locally verified:** Tasks and job monitoring (0.6.0). Publish the release commit and verify its platform CI before starting module 2 implementation.
2. **Pending:** Modules 2–13 in roadmap order.

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
- Remote commit and platform CI are verified after publication; see the GitHub compatibility workflow attached to the release commit.

### Next release

Module 2: model management, target 0.7.0. Contract audit may proceed while the 0.6.0 release checks finish; implementation starts after publication is verified.
