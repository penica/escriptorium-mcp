#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mcp-skills-test.XXXXXX")"
trap 'rm -rf -- "$test_dir"' EXIT
export ESCRIPTORIUM_SKILLS_DIR="$test_dir/client skills"
export SKILL_TEST_ASSETS="$test_dir/assets"
mkdir -p "$SKILL_TEST_ASSETS" "$test_dir/bin" "$test_dir/bundle/escriptorium-mcp-0.18.0-wsl/skills"
bundle="$test_dir/bundle/escriptorium-mcp-0.18.0-wsl"
cp -R "$repo_dir/skills/escriptorium" "$bundle/skills/"
mkdir "$bundle/docs"
printf 'fixture reference\n' > "$bundle/docs/FONTS-API.md"
(cd "$bundle" && shasum -a 256 skills/escriptorium/SKILL.md skills/escriptorium/agents/openai.yaml docs/FONTS-API.md > SHA256SUMS)
archive=escriptorium-mcp-0.18.0-wsl.tar.gz
tar -czf "$SKILL_TEST_ASSETS/$archive" -C "$test_dir/bundle" escriptorium-mcp-0.18.0-wsl
(cd "$SKILL_TEST_ASSETS" && shasum -a 256 "$archive" > "$archive.sha256")
cp "$SKILL_TEST_ASSETS/$archive.sha256" "$test_dir/checksum.good"
cat > "$test_dir/bin/curl" <<'SH'
#!/bin/sh
set -eu
for arg in "$@"; do
    case "$arg" in
        */releases/latest) printf 'https://github.com/penica/escriptorium-mcp/releases/tag/v0.18.0'; exit ;;
        https://*) source=${arg##*/} ;;
    esac
done
[ "${SKILL_DOWNLOAD_FAIL:-no}" != yes ] || exit 22
while [ "$1" != -o ]; do shift; done
cp "$SKILL_TEST_ASSETS/$source" "$2"
SH
chmod +x "$test_dir/bin/curl"
export PATH="$test_dir/bin:$PATH"
run_install() { cat "$repo_dir/install-skills.sh" | sh -s -- "$@" > "$test_dir/output" 2>&1; }
run_install
cmp "$repo_dir/skills/escriptorium/SKILL.md" "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/SKILL.md"
test -f "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/docs/FONTS-API.md"
printf 'PASS: piped first skill install and bundled references\n'
run_install
grep -q 'already matches' "$test_dir/output"
test ! -e "$test_dir/skill-backups"
printf 'PASS: unchanged skill does not create backups\n'
printf '\nlocal customization\n' >> "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/SKILL.md"
cp "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/SKILL.md" "$test_dir/customized"
run_install 0.18.0
backup=$(find "$test_dir/skill-backups" -name SKILL.md)
cmp "$backup" "$test_dir/customized"
cmp "$repo_dir/skills/escriptorium/SKILL.md" "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/SKILL.md"
printf 'PASS: prior local changes backed up outside scanned skills\n'
printf 'bad checksum\n' > "$SKILL_TEST_ASSETS/$archive.sha256"
if run_install; then exit 1; fi
cmp "$repo_dir/skills/escriptorium/SKILL.md" "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/SKILL.md"
test ! -e "$test_dir/.escriptorium-skill-install.lock"
cp "$test_dir/checksum.good" "$SKILL_TEST_ASSETS/$archive.sha256"
printf 'PASS: checksum failure leaves existing skill intact\n'
if SKILL_DOWNLOAD_FAIL=yes run_install; then exit 1; fi
cmp "$repo_dir/skills/escriptorium/SKILL.md" "$ESCRIPTORIUM_SKILLS_DIR/escriptorium/SKILL.md"
printf 'PASS: download failure leaves existing skill intact\n'
mkdir "$test_dir/.escriptorium-skill-install.lock"
if run_install; then exit 1; fi
rmdir "$test_dir/.escriptorium-skill-install.lock"
printf 'PASS: concurrent install refused\n'
mv "$ESCRIPTORIUM_SKILLS_DIR/escriptorium" "$test_dir/linked skill"
ln -s "$test_dir/linked skill" "$ESCRIPTORIUM_SKILLS_DIR/escriptorium"
if run_install; then exit 1; fi
test -L "$ESCRIPTORIUM_SKILLS_DIR/escriptorium"
printf 'PASS: existing symlink target is not overwritten\n'
