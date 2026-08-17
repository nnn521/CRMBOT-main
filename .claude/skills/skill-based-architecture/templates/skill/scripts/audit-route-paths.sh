#!/usr/bin/env bash
# audit-route-paths.sh — Report which routes can activate rules/ and references/.
#
# Usage:
#   bash scripts/audit-route-paths.sh [skill-name|skill-root] [--manifest path] [--strict]
#
# Default mode reports only. --strict exits 1 when a rules/ or references/ file
# has no route path. A route path means the file is in always_read, in a task's
# required_reads/route text, or linked from that task's workflow/read files.

set -euo pipefail

TARGET="."
MANIFEST=""
STRICT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest)
      [[ $# -ge 2 ]] || { echo "Missing value for --manifest" >&2; exit 2; }
      MANIFEST="$2"
      shift 2
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      TARGET="$1"
      shift
      ;;
  esac
done

if [[ -f "$TARGET/SKILL.md" || -f "$TARGET/SKILL.md.template" ]]; then
  ROOT="${TARGET%/}"
elif [[ -f "skills/$TARGET/SKILL.md" ]]; then
  ROOT="skills/$TARGET"
elif [[ -f "SKILL.md" || -f "SKILL.md.template" ]]; then
  ROOT="."
else
  echo "Usage: bash audit-route-paths.sh [skill-name|skill-root] [--manifest path] [--strict]" >&2
  exit 2
fi

if [[ -z "$MANIFEST" ]]; then
  if [[ -f "$ROOT/routing.yaml" ]]; then
    MANIFEST="$ROOT/routing.yaml"
  elif [[ -f "$ROOT/references/self-hosting-routing.yaml" ]]; then
    MANIFEST="$ROOT/references/self-hosting-routing.yaml"
  else
    echo "No routing manifest found under $ROOT" >&2
    exit 2
  fi
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "Missing manifest: $MANIFEST" >&2
  exit 2
fi

strip_anchor() {
  printf '%s' "$1" | sed 's/#.*$//'
}

file_mentions() {
  local needle="$1" file="$2"
  [[ -f "$file" ]] || return 1
  grep -qF "$needle" "$file"
}

task_block() {
  local id="$1"
  awk -v id="$id" '
    /^[[:space:]]*-[[:space:]]id:/ {
      current=$0
      sub(/^[[:space:]]*-[[:space:]]id:[[:space:]]*/, "", current)
      in_task=(current==id)
    }
    in_task { print }
  ' "$MANIFEST"
}

task_ids() {
  awk '
    /^[[:space:]]*-[[:space:]]id:/ {
      id=$0
      sub(/^[[:space:]]*-[[:space:]]id:[[:space:]]*/, "", id)
      gsub(/["'\'']/, "", id)
      print id
    }
  ' "$MANIFEST"
}

always_read_mentions() {
  local target="$1"
  awk -v target="$target" '
    /^always_read:/ { in_list=1; next }
    in_list && /^[A-Za-z0-9_-]+:/ { exit }
    in_list && index($0, target) { found=1 }
    END { exit found ? 0 : 1 }
  ' "$MANIFEST"
}

routes_for_target() {
  local target="$1"
  local routes=()
  local id block workflow read_file

  if always_read_mentions "$target"; then
    routes+=("always_read")
  fi

  while IFS= read -r id; do
    [[ -n "$id" ]] || continue
    block="$(task_block "$id")"

    if printf '%s\n' "$block" | grep -qF "$target"; then
      routes+=("$id")
      continue
    fi

    workflow="$(printf '%s\n' "$block" | awk '/^[[:space:]]*workflow:/ { sub(/^[[:space:]]*workflow:[[:space:]]*/, ""); gsub(/["'\'']/, ""); print; exit }')"
    workflow="$(strip_anchor "$workflow")"
    if [[ -n "$workflow" && -f "$ROOT/$workflow" ]] && file_mentions "$target" "$ROOT/$workflow"; then
      routes+=("$id")
      continue
    fi

    while IFS= read -r read_file; do
      read_file="$(strip_anchor "$read_file")"
      case "$(basename "$read_file")" in SKILL.md|SKILL.md.template) continue ;; esac
      [[ -f "$ROOT/$read_file" ]] || continue
      if file_mentions "$target" "$ROOT/$read_file"; then
        routes+=("$id")
        break
      fi
    done < <(printf '%s\n' "$block" | awk '
      /^[[:space:]]*required_reads:/ { in_reads=1; next }
      in_reads && /^[[:space:]]{4}[A-Za-z0-9_-]+:/ { exit }
      in_reads && /^[[:space:]]*-[[:space:]]/ {
        line=$0
        sub(/^[[:space:]]*-[[:space:]]*/, "", line)
        gsub(/["'\'']/, "", line)
        print line
      }
    ')
  done < <(task_ids)

  if [[ ${#routes[@]} -gt 0 ]]; then
    printf '%s\n' "${routes[@]}" | awk '!seen[$0]++' | paste -sd ',' -
  fi
}

echo "Route Path Audit"
echo "================"
echo "Root: $ROOT"
echo "Manifest: $MANIFEST"
echo ""
printf '%-44s %s\n' "FILE" "ROUTE PATHS"
printf '%-44s %s\n' "----" "-----------"

unreachable=0
audited=0
for dir in references rules; do
  [[ -d "$ROOT/$dir" ]] || continue
  for f in "$ROOT/$dir"/*.md; do
    [[ -f "$f" ]] || continue
    case "$(basename "$f")" in README.md|index.md) continue ;; esac
    rel="${f#$ROOT/}"
    routes="$(routes_for_target "$rel" || true)"
    audited=$((audited+1))
    if [[ -n "$routes" ]]; then
      printf '%-44s %s\n' "$rel" "$routes"
    else
      printf '%-44s %s\n' "$rel" "NO ROUTE PATH"
      unreachable=$((unreachable+1))
    fi
  done
done

echo ""
echo "Summary: $audited file(s) audited, $unreachable without route path."
if [[ "$STRICT" -eq 1 && "$unreachable" -gt 0 ]]; then
  exit 1
fi
exit 0
