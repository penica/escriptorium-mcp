#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export QA_PYTHON="${QA_PYTHON:-$repo_dir/.venv/bin/python}"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mcp-update-test.XXXXXX")"
trap 'rm -rf -- "$test_dir"' EXIT
export TEST_ROOT="$test_dir"
export ESCRIPTORIUM_INSTALL_DIR="$test_dir/install with spaces"
export XDG_CONFIG_HOME="$test_dir/user config"
mkdir -p "$XDG_CONFIG_HOME/systemd/user"
printf 'fixture service\n' > "$XDG_CONFIG_HOME/systemd/user/escriptorium-mcp.service"
mkdir -p "$test_dir/bin" "$ESCRIPTORIUM_INSTALL_DIR/.venv/bin"
export PATH="$test_dir/bin:$PATH"
cat > "$test_dir/bin/curl" <<'SH'
#!/bin/sh
set -eu
for arg in "$@"; do
    case "$arg" in
        */releases/latest) printf 'https://github.com/penica/escriptorium-mcp/releases/tag/v0.18.0'; exit ;;
        https://*) source=${arg##*/} ;;
    esac
done
[ "${FAIL_DOWNLOAD:-no}" != yes ] || exit 22
while [ "$1" != -o ]; do shift; done
cp "$TEST_ROOT/$source" "$2"
SH
cat > "$test_dir/bin/systemctl" <<'SH'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$TEST_ROOT/service.log"
case "$2" in
    cat) [ "${MISSING_SERVICE:-no}" != yes ] ;;
    stop) printf stopped > "$TEST_ROOT/state" ;;
    restart) printf active > "$TEST_ROOT/state" ;;
    is-active) [ "$(cat "$TEST_ROOT/state")" = active ] ;;
esac
SH
cat > "$test_dir/bin/uv" <<'SH'
#!/bin/sh
exit 0
SH
cat > "$ESCRIPTORIUM_INSTALL_DIR/.venv/bin/python" <<'SH'
#!/bin/sh
case "$2" in
    *importlib.metadata*) cat "$TEST_ROOT/version" ;;
    *) exec "$QA_PYTHON" "$@" ;;
esac
SH
chmod +x "$test_dir/bin/"* "$ESCRIPTORIUM_INSTALL_DIR/.venv/bin/python"
cat > "$ESCRIPTORIUM_INSTALL_DIR/config.env" <<'ENV'
ESCRIPTORIUM_URL=http://fixture.invalid/
ESCRIPTORIUM_API_KEY=fixture-key
ESCRIPTORIUM_HTTP_TOKEN=fixture-token
ENV
cp "$ESCRIPTORIUM_INSTALL_DIR/config.env" "$test_dir/config.expected"
bundle="$test_dir/escriptorium-mcp-0.18.0-wsl"
mkdir "$bundle"
cat > "$bundle/install.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
test "$1" = "$ESCRIPTORIUM_INSTALL_DIR"
cat > "$TEST_ROOT/answers"
printf '\n\n1\ny\nn\n' > "$TEST_ROOT/expected-answers"
cmp "$TEST_ROOT/answers" "$TEST_ROOT/expected-answers"
[ "${FAIL_INSTALL:-no}" != yes ] || exit 17
printf '0.18.0\n' > "$TEST_ROOT/version"
systemctl --user restart escriptorium-mcp
SH
(cd "$bundle" && shasum -a 256 install.sh > SHA256SUMS)
tar -czf "$test_dir/escriptorium-mcp-0.18.0-wsl.tar.gz" -C "$test_dir" escriptorium-mcp-0.18.0-wsl
(cd "$test_dir" && shasum -a 256 escriptorium-mcp-0.18.0-wsl.tar.gz > escriptorium-mcp-0.18.0-wsl.tar.gz.sha256)
cp "$test_dir/escriptorium-mcp-0.18.0-wsl.tar.gz.sha256" "$test_dir/checksum.expected"
reset_case() {
    printf '0.5.0\n' > "$test_dir/version"
    printf active > "$test_dir/state"
    : > "$test_dir/service.log"
}
run_update() { cat "$repo_dir/update.sh" | sh -s -- "$@" > "$test_dir/output" 2>&1; }
expect_unchanged() {
    test "$(cat "$test_dir/state")" = active
    if grep -q -- '--user stop' "$test_dir/service.log"; then exit 1; fi
    cmp "$test_dir/config.expected" "$ESCRIPTORIUM_INSTALL_DIR/config.env"
}
reset_case
run_update
grep -q 'Updated to 0.18.0' "$test_dir/output"
test "$(cat "$test_dir/state")" = active
cmp "$test_dir/config.expected" "$ESCRIPTORIUM_INSTALL_DIR/config.env"
test ! -e "$ESCRIPTORIUM_INSTALL_DIR/.update-lock"
printf 'PASS: piped latest upgrade, automatic answers, configuration and restart\n'
: > "$test_dir/service.log"
run_update
grep -q 'Already on 0.18.0' "$test_dir/output"
expect_unchanged
printf 'PASS: already-current no-op\n'
reset_case
printf 'bad checksum\n' > "$test_dir/escriptorium-mcp-0.18.0-wsl.tar.gz.sha256"
if run_update; then exit 1; fi
expect_unchanged
test ! -e "$ESCRIPTORIUM_INSTALL_DIR/.update-lock"
cp "$test_dir/checksum.expected" "$test_dir/escriptorium-mcp-0.18.0-wsl.tar.gz.sha256"
printf 'PASS: checksum failure before service stop, lock cleanup\n'
reset_case
if FAIL_DOWNLOAD=yes run_update; then exit 1; fi
expect_unchanged
printf 'PASS: download failure before service stop\n'
reset_case
if MISSING_SERVICE=yes run_update; then exit 1; fi
expect_unchanged
printf 'PASS: missing service refusal\n'
reset_case
printf '0.19.0\n' > "$test_dir/version"
if run_update 0.18.0; then exit 1; fi
expect_unchanged
printf 'PASS: downgrade refusal\n'
reset_case
mkdir "$ESCRIPTORIUM_INSTALL_DIR/.update-lock"
if run_update; then exit 1; fi
expect_unchanged
rmdir "$ESCRIPTORIUM_INSTALL_DIR/.update-lock"
printf 'PASS: concurrent updater refusal\n'
reset_case
if FAIL_INSTALL=yes run_update 0.18.0; then exit 1; fi
test "$(cat "$test_dir/state")" = stopped
grep -q 'No automatic rollback' "$test_dir/output"
test ! -e "$ESCRIPTORIUM_INSTALL_DIR/.update-lock"
printf 'PASS: installer failure is reported without claiming success\n'
printf '0.18.0\n' > "$test_dir/version"
run_update
grep -q 'Updated to 0.18.0' "$test_dir/output"
test ! -e "$ESCRIPTORIUM_INSTALL_DIR/.update-incomplete"
test "$(cat "$test_dir/state")" = active
printf 'PASS: interrupted update can finish even after the version changed\n'
