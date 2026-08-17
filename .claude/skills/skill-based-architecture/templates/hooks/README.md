# hooks/ - Harness Integration Points

Three hooks ship here. All are **opt-in**. Copy the scripts and JSON for the harness you use; context-injection scripts exit silently when their inputs are absent.

| Hook | Script | Fires on | Purpose |
|---|---|---|---|
| SessionStart | `session-start` | startup / `/clear` / `/compact` | Re-inject one router file so routing survives context summarization |
| UserPromptSubmit | `workflow-state` | every user prompt | Inject one active long-workflow hint from `.skill-workflow-state` |
| PreToolUse | `agent-behavior-gate.sh` | every Write/Edit | Enforce the Admission Threshold for `rules/agent-behavior.md` |

See `SECURITY.md` for the trust boundary around hook-read files.

## SessionStart Policy

The SessionStart hook injects **navigation, not the knowledge base**. It never reads every `skills/*/SKILL.md`.

Resolution order:

1. `SKILL_ROUTER_PATH` - explicit router for multi-skill repos
2. `SKILL_PATH` - backward-compatible explicit single-skill path
3. `skills/router/SKILL.md` - conventional multi-skill router
4. Exactly one `skills/*/SKILL.md` - single-skill fallback

If multiple skill entries exist and no router is configured, the hook injects nothing rather than guessing.

## Workflow-State Policy

`workflow-state` is for long workflows only. It reads `.skill-workflow-state` by default:

```text
workflow=skills/<name>/workflows/plan-feature.md
status=planning
task=docs/plans/YYYY-MM-DD-slug
```

The workflow file owns the prompt text through `[workflow-state:<status>]` blocks. Missing state file, missing workflow file, or unknown status exits 0 with no output, so short tasks stay quiet. Delete `.skill-workflow-state` when the workflow completes or is abandoned.

Overrides:

| Variable | Purpose |
|---|---|
| `SKILL_WORKFLOW_STATE_FILE` | Use a non-default state file |
| `SKILL_WORKFLOW_FILE` | Fallback workflow file when the state omits `workflow=` |
| `CLAUDE_HARNESS` / `SESSION_HARNESS` | Select output shape: `claude`, `cursor`, `gemini`, or fallback |

## Agent-Behavior Gate

The Admission Threshold in `templates/ANTI-TEMPLATES.md` is a convention gate. Tested against 10 adversarial prompts, it blocked ~30% on Sonnet and ~11% on Haiku. `agent-behavior-gate.sh` turns that rule into a deterministic interactive PreToolUse gate.

Install when:

- Multiple people edit `rules/agent-behavior.md`
- The repo is product-critical
- Any committer uses Haiku-class models

Do not rely on it alone for automation: `claude --print` and agent-dispatched edits can bypass blocking. Use CODEOWNERS/CI for those surfaces.

False-positive controls:

- Shrinking edits pass
- Same-line typo/style fixes within `AGENT_BEHAVIOR_GATE_TYPO_TOLERANCE` pass
- `AGENT_BEHAVIOR_GATE_OVERRIDE=1` bypasses with a stderr acknowledgement
- `AGENT_BEHAVIOR_GATE_WARN=1` reports would-block reasons but exits 0

## Install - Claude Code

```bash
mkdir -p .claude/hooks
cp templates/hooks/session-start .claude/hooks/session-start
cp templates/hooks/workflow-state .claude/hooks/workflow-state
cp templates/hooks/agent-behavior-gate.sh .claude/hooks/agent-behavior-gate.sh
chmod +x .claude/hooks/session-start .claude/hooks/workflow-state .claude/hooks/agent-behavior-gate.sh
test -f .claude/settings.json || cp templates/hooks/hooks.json .claude/settings.json
```

If `.claude/settings.json` already exists, merge the top-level `hooks` object from `templates/hooks/hooks.json`.

`workflow-state` only reads relative workflow files under `workflows/`, `skills/*/workflows/`, or `templates/skill/workflows/`; absolute paths, `..`, and symlinks are ignored. `agent-behavior-gate.sh` needs `jq` because it parses tool-input JSON. The other two scripts need only bash and python3.

Schema check: Claude Code CLI v2.1+ uses the nested hook format (`matcher` -> `hooks[]` -> `{type,command}`). If a hook appears configured but does not fire, inspect hook events with the CLI's verbose hook output.
<!-- external-fact: verified=2026-05-06 source=https://code.claude.com/docs/en/hooks -->

## Install - Cursor

```bash
mkdir -p .cursor/hooks
cp templates/hooks/session-start .cursor/hooks/session-start
cp templates/hooks/workflow-state .cursor/hooks/workflow-state
cp templates/hooks/agent-behavior-gate.sh .cursor/hooks/agent-behavior-gate.sh
chmod +x .cursor/hooks/session-start .cursor/hooks/workflow-state .cursor/hooks/agent-behavior-gate.sh
cp templates/hooks/hooks-cursor.json .cursor/hooks.json
```

Cursor's hook contracts may differ from Claude Code's. Verify each hook fires before treating it as enforcement.

## Install - Other Harnesses

`session-start` and `workflow-state` write small JSON context payloads. `agent-behavior-gate.sh` reads Claude-Code-compatible tool JSON on stdin, writes reasons to stderr, and exits 0/2. Harnesses with different contracts need a thin adapter around these scripts.

## Tuning

| Variable | Default | Applies to |
|---|---|---|
| `AGENT_BEHAVIOR_GATE_HARD_CAP` | 100 | Maximum allowed `agent-behavior.md` lines |
| `AGENT_BEHAVIOR_GATE_TYPO_TOLERANCE` | 20 | Same-line typo/style tolerance |
| `AGENT_BEHAVIOR_GATE_PATH` | `templates/skill/rules/agent-behavior.md` | Gated file path |
| `AGENT_BEHAVIOR_GATE_EVIDENCE` | `templates/skill/references/behavior-failures.md` | Evidence file path |

## Dry Runs

```bash
# SessionStart: outputs JSON only when it can resolve exactly one router.
CLAUDE_HARNESS=claude bash .claude/hooks/session-start

# Workflow state: no state file should be a quiet pass.
bash .claude/hooks/workflow-state

# Behavior gate: pipe simulated hook input JSON when testing outside the runtime.
bash .claude/hooks/agent-behavior-gate.sh < /tmp/hook-input.json
```
