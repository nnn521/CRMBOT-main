#!/usr/bin/env bash
# check-growth-health.sh — Report skill/template growth pressure without failing.
#
# Usage:
#   bash scripts/check-growth-health.sh [skill-name|skill-root]
#   bash skills/<name>/scripts/check-growth-health.sh <name>
#
# This is a report, not a gate. It exits 0 so teams can first make growth
# pressure visible before deciding which thresholds should become hard checks.

set -euo pipefail

TARGET="${1:-.}"

if [[ -f "$TARGET/SKILL.md" || -f "$TARGET/SKILL.md.template" ]]; then
  ROOT="${TARGET%/}"
elif [[ -f "skills/$TARGET/SKILL.md" ]]; then
  ROOT="skills/$TARGET"
elif [[ -f "SKILL.md" || -f "SKILL.md.template" ]]; then
  ROOT="."
else
  echo "Usage: bash check-growth-health.sh [skill-name|skill-root]" >&2
  exit 2
fi

WATCH=0
REVIEW=0

status_line() {
  local status="$1" label="$2" detail="$3"
  printf '%-6s %-42s %s\n' "$status" "$label" "$detail"
  case "$status" in
    WATCH) WATCH=$((WATCH+1)) ;;
    REVIEW) REVIEW=$((REVIEW+1)) ;;
  esac
}

line_count() {
  [[ -f "$1" ]] || { echo 0; return; }
  wc -l < "$1" | tr -d ' '
}

check_lines() {
  local file="$1" max="$2" label="$3"
  [[ -f "$file" ]] || return
  local lines
  lines="$(line_count "$file")"
  if [[ "$lines" -gt "$max" ]]; then
    status_line "REVIEW" "$label" "$lines lines > $max"
  elif [[ "$lines" -ge $((max * 9 / 10)) ]]; then
    status_line "WATCH" "$label" "$lines lines near $max"
  else
    status_line "OK" "$label" "$lines lines <= $max"
  fi
}

count_always_read() {
  local manifest="$1"
  awk '
    /^always_read:/ { in_list=1; next }
    in_list && /^[A-Za-z0-9_-]+:/ { exit }
    in_list && /^[[:space:]]*-[[:space:]]/ { count++ }
    END { print count+0 }
  ' "$manifest"
}

count_tasks() {
  grep -E '^[[:space:]]*-[[:space:]]id:' "$1" 2>/dev/null | wc -l | tr -d ' '
}

check_manifest() {
  local manifest="$1" label="$2"
  [[ -f "$manifest" ]] || return 0

  local always tasks
  always="$(count_always_read "$manifest")"
  tasks="$(count_tasks "$manifest")"

  if [[ "$always" -gt 0 ]]; then
    if [[ "$always" -gt 3 ]]; then
      status_line "REVIEW" "$label always_read" "$always files > 3"
    elif [[ "$always" -eq 3 ]]; then
      status_line "WATCH" "$label always_read" "$always files at upper bound"
    else
      status_line "OK" "$label always_read" "$always files"
    fi
  fi

  if [[ "$tasks" -gt 10 ]]; then
    status_line "REVIEW" "$label routes" "$tasks routes > 10"
  elif [[ "$tasks" -ge 9 ]]; then
    status_line "WATCH" "$label routes" "$tasks routes near 10"
  else
    status_line "OK" "$label routes" "$tasks routes"
  fi
}

check_workflows() {
  local dir="$1"
  [[ -d "$dir/workflows" ]] || return 0
  local f base max
  for f in "$dir"/workflows/*.md; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    case "$base" in
      update-rules.md|maintain-docs.md|subagent-driven.md) max=250 ;;
      *) max=100 ;;
    esac
    check_lines "$f" "$max" "workflow/$base"
  done
}

check_scripts() {
  local dir="$1"
  [[ -d "$dir/scripts" ]] || return 0
  local f base max
  for f in "$dir"/scripts/*.sh; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    case "$base" in
      smoke-test.sh) max=800 ;;
      test-trigger.sh) max=360 ;;
      sync-routing.sh) max=320 ;;
      audit-route-paths.sh) max=280 ;;
      check-growth-health.sh) max=220 ;;
      check-description-routing.sh) max=160 ;;
      check-external-facts.sh) max=120 ;;
      *) max=220 ;;
    esac
    check_lines "$f" "$max" "script/$base"
  done
}

echo "Growth Health Report"
echo "===================="
echo "Root: $ROOT"
echo ""

if [[ -f "$ROOT/SKILL.md" ]]; then
  check_lines "$ROOT/SKILL.md" 100 "SKILL.md"
elif [[ -f "$ROOT/SKILL.md.template" ]]; then
  check_lines "$ROOT/SKILL.md.template" 100 "SKILL.md.template"
fi

check_manifest "$ROOT/routing.yaml" "routing.yaml"
check_workflows "$ROOT"
check_scripts "$ROOT"

if [[ -d "$ROOT/templates/skill" ]]; then
  check_lines "$ROOT/templates/skill/SKILL.md.template" 100 "template SKILL.md"
  check_manifest "$ROOT/templates/skill/routing.yaml" "template routing.yaml"
  check_workflows "$ROOT/templates/skill"
  check_scripts "$ROOT/templates/skill"
fi

if [[ -f "$ROOT/references/self-hosting-routing.yaml" ]]; then
  check_manifest "$ROOT/references/self-hosting-routing.yaml" "self-hosting routing"
fi

echo ""
echo "Summary: $WATCH watch, $REVIEW review. Report only; exit code is always 0."
exit 0
