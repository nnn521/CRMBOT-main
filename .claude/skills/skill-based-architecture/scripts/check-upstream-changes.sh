#!/usr/bin/env bash
# Require upstream update notes when downstream-facing upstream files change.

set -euo pipefail

BASE="${UPSTREAM_CHANGES_BASE:-HEAD}"
MODE="worktree"

usage() {
  cat <<'EOF'
Usage: scripts/check-upstream-changes.sh [--base <git-ref>] [--staged]

Fails when downstream-facing upstream files changed but UPSTREAM-CHANGES.md did
not change in the same diff. If a watched change has no downstream refresh
impact, add a short "no downstream impact" entry to UPSTREAM-CHANGES.md.

Default mode checks staged, unstaged, and untracked files. Use --staged from a
pre-commit hook to verify only the pending commit.

Watched areas:
  templates/**
  references/**
  WORKFLOW.md
  TEMPLATES-GUIDE.md
  README.md
  README.zh-CN.md
  skill.yaml
  scripts/check-all.sh
  scripts/check-upstream-changes.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      [[ $# -ge 2 ]] || { echo "Missing value for --base" >&2; exit 2; }
      BASE="$2"
      shift 2
      ;;
    --staged)
      MODE="staged"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "FAIL: not inside a git repository" >&2
  exit 1
fi
cd "$ROOT"

if ! git rev-parse --verify "$BASE^{commit}" >/dev/null 2>&1; then
  echo "FAIL: base ref does not exist: $BASE" >&2
  exit 1
fi

is_watched() {
  case "$1" in
    templates/*) return 0 ;;
    references/*) return 0 ;;
    WORKFLOW.md) return 0 ;;
    TEMPLATES-GUIDE.md) return 0 ;;
    README.md) return 0 ;;
    README.zh-CN.md) return 0 ;;
    skill.yaml) return 0 ;;
    scripts/check-all.sh) return 0 ;;
    scripts/check-upstream-changes.sh) return 0 ;;
    *) return 1 ;;
  esac
}

if [[ "$MODE" == "staged" ]]; then
  changed_paths="$(git diff --cached --name-only "$BASE" -- | sed '/^$/d' | sort -u)"
else
  changed_paths="$(
    {
      git diff --name-only "$BASE" --
      git ls-files --others --exclude-standard
    } | sed '/^$/d' | sort -u
  )"
fi

if [[ -z "$changed_paths" ]]; then
  echo "OK: no $MODE changes relative to $BASE"
  exit 0
fi

note_changed=false
watched_paths=""

while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  if [[ "$path" == "UPSTREAM-CHANGES.md" ]]; then
    note_changed=true
    continue
  fi
  if is_watched "$path"; then
    watched_paths="${watched_paths}${path}"$'\n'
  fi
done <<< "$changed_paths"

if [[ -z "$watched_paths" ]]; then
  echo "OK: no downstream-facing upstream files changed"
  exit 0
fi

if $note_changed; then
  echo "OK: downstream-facing upstream changes include UPSTREAM-CHANGES.md"
  exit 0
fi

cat >&2 <<EOF
FAIL: downstream-facing upstream files changed, but UPSTREAM-CHANGES.md did not.

Changed watched files:
$watched_paths
Add an UPSTREAM-CHANGES.md entry in the same commit. If this change has no
downstream refresh impact, write that explicitly in UPSTREAM-CHANGES.md instead
of bypassing the check silently.
EOF
exit 1
