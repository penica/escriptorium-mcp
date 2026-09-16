#!/bin/sh
main() {
    set -eu
    umask 077
    fail() { printf '%s\n' "$*" >&2; exit 1; }
    [ "$(id -u)" != 0 ] || fail 'Run as the user who runs Codex, without sudo.'
    [ "$#" -le 1 ] || fail 'Usage: sh install-skills.sh [0.18.0]'
    skills_root=${ESCRIPTORIUM_SKILLS_DIR:-}
    if [ -z "$skills_root" ]; then
        skills_root="$HOME/.agents/skills"
        legacy_root="${CODEX_HOME:-$HOME/.codex}/skills"
        if [ -e "$legacy_root/escriptorium" ]; then
            [ ! -e "$skills_root/escriptorium" ] || fail 'Two eScriptorium skills exist. Set ESCRIPTORIUM_SKILLS_DIR to the one you want to update.'
            skills_root=$legacy_root
        fi
    fi
    case "$skills_root" in /*) ;; *) fail 'ESCRIPTORIUM_SKILLS_DIR must be absolute.' ;; esac
    target="$skills_root/escriptorium"
    [ ! -L "$target" ] || fail 'The existing skill is a symlink. Set ESCRIPTORIUM_SKILLS_DIR to its real parent directory.'
    [ ! -e "$target" ] || [ -d "$target" ] || fail 'The skill destination is not a directory.'
    mkdir -p "$skills_root"
    parent=$(cd "$skills_root/.." && pwd)
    lock="$parent/.escriptorium-skill-install.lock"
    mkdir "$lock" 2>/dev/null || fail 'Another skill installation may be running.'
    work_dir=
    backup=
    cleanup() {
        result=$?
        trap - EXIT
        if [ "$result" -ne 0 ] && [ -n "$backup" ] && [ ! -e "$target" ]; then mv "$backup" "$target"; fi
        [ -z "$work_dir" ] || rm -rf -- "$work_dir"
        rmdir "$lock"
        exit "$result"
    }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    work_dir=$(mktemp -d "$parent/.escriptorium-skill-stage.XXXXXX")
    cd "$work_dir"
    repo_url=https://github.com/penica/escriptorium-mcp
    version=${1:-}
    if [ -z "$version" ]; then
        latest_url=$(curl -fsSL --connect-timeout 20 --max-time 120 -o /dev/null -w '%{url_effective}' "$repo_url/releases/latest")
        case "$latest_url" in "$repo_url/releases/tag/v"*) version=${latest_url##*/v} ;; *) fail 'GitHub did not return a release tag.' ;; esac
    fi
    printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail 'Expected a stable version such as 0.18.0.'
    archive="escriptorium-mcp-$version-wsl.tar.gz"
    curl -fsSL --connect-timeout 20 --max-time 300 "$repo_url/releases/download/v$version/$archive" -o "$archive"
    curl -fsSL --connect-timeout 20 --max-time 120 "$repo_url/releases/download/v$version/$archive.sha256" -o "$archive.sha256"
    read -r checksum filename extra < "$archive.sha256"
    [ "$filename" = "$archive" ] && [ -z "$extra" ] || fail 'Unexpected release checksum file.'
    printf '%s\n' "$checksum" | grep -Eq '^[a-fA-F0-9]{64}$' || fail 'Invalid release checksum.'
    if command -v sha256sum >/dev/null 2>&1; then hash_command=sha256sum; else hash_command='shasum -a 256'; fi
    # Only the fixed archive filename is passed to the checksum verifier.
    printf '%s  %s\n' "$checksum" "$archive" | $hash_command --check -
    tar -xzf "$archive"
    cd "escriptorium-mcp-$version-wsl"
    $hash_command --check SHA256SUMS
    source_dir="$work_dir/escriptorium-mcp-$version-wsl/skills/escriptorium"
    [ -s "$source_dir/SKILL.md" ] || fail 'The release contains no eScriptorium skill.'
    cp -R docs "$source_dir/docs"
    printf '%s\n' "$version" > "$source_dir/.escriptorium-release"
    if [ -d "$target" ] && diff -qr "$source_dir" "$target" >/dev/null 2>&1; then
        printf 'Skill already matches release %s at %s\n' "$version" "$target"
        return
    fi
    if [ -d "$target" ]; then
        mkdir -p "$parent/skill-backups"
        backup_dir=$(mktemp -d "$parent/skill-backups/escriptorium.XXXXXX")
        backup="$backup_dir/escriptorium"
        mv "$target" "$backup"
    fi
    mv "$source_dir" "$target"
    [ -z "$backup" ] || printf 'Previous skill backed up to %s\n' "$backup"
    printf 'Installed eScriptorium skill from %s at %s\nAvailable on your next Codex turn; restart Codex if it does not appear.\n' "$version" "$target"
    printf '%s\n' 'Your MCP connection and credentials were not changed.'
}

main "$@"
