# Reference

Look up what you need, not everything. Reference topics live under [`references/`](references/) split by subject.

## By task

- **Laying out a new skill** → [`references/layout.md`](references/layout.md)
- **Deciding when to grow / shrink / split a skill** → [`references/progressive-rigor.md`](references/progressive-rigor.md)
- **Diagnosing instability — is it prompt, context, or harness?** → [`references/layout.md § Positioning in the Agent Stack`](references/layout.md#positioning-in-the-agent-stack)
- **Writing or debugging thin shells** → [`references/thin-shells.md`](references/thin-shells.md) (common body, hooks, hygiene); [`references/per-tool-shells.md`](references/per-tool-shells.md) (per-tool templates + compatibility matrix)
- **Updating downstream task routing** → edit `skills/<name>/routing.yaml`, then `bash skills/<name>/scripts/sync-routing.sh <name> --check`
- **Updating this repo's self-hosting shell routes** → edit [`references/self-hosting-routing.yaml`](references/self-hosting-routing.yaml), then `bash scripts/sync-self-routing.sh` + `bash scripts/check-self-routing.sh`
- **Task Closure Protocol, recording lessons, or activation verification** → [`references/protocols.md`](references/protocols.md)
- **Operating a multi-skill repo (routing, fission signals, coexistence rules)** → [`references/multi-skill-routing.md`](references/multi-skill-routing.md)
- **Composing other skills from your workflows** → [`references/skill-composition.md`](references/skill-composition.md)
- **Picking rule file sets, anti-patterns, file size budgets, troubleshooting** → [`references/conventions.md`](references/conventions.md)

## By topic

| File | Covers |
|---|---|
| [layout.md](references/layout.md) | Recommended directory layout, `SKILL.md` template, description-as-trigger discipline, positioning in the agent stack, relation to the official Anthropic skill spec |
| [progressive-rigor.md](references/progressive-rigor.md) | Three structural tiers (Single-file / Folder-light / Full), upgrade triggers, three-axis profile (structure / execution / topology), Simple vs Advanced route schema |
| [thin-shells.md](references/thin-shells.md) | Cursor registration entry, common thin-shell body, Auto-Triggers, XML-Tag Injection, SessionStart hook, Context Hygiene Playbook |
| [per-tool-shells.md](references/per-tool-shells.md) | Per-tool shell templates (AGENTS / CLAUDE / CODEX / GEMINI / Cursor / Windsurf / Claude native) + tool compatibility matrix |
| [protocols.md](references/protocols.md) | Task Closure Protocol, recording threshold (2/3), recording destination guide, generalization rule, when references alone are not enough, skill activation verification |
| [multi-skill-routing.md](references/multi-skill-routing.md) | Multi-skill repo operating guide: routing, description discipline, shared resources, cross-skill refs, fission signals, coexistence rules |
| [skill-composition.md](references/skill-composition.md) | Composing other skills from your workflows (embedded / serial chain / subagent delegation) |
| [executable-skill-architecture.md](references/executable-skill-architecture.md) | Optional advanced shape for API/CLI/platform-operation skills with scripts, tools, capabilities, workflows, and local config |
| [scenario-testing.md](references/scenario-testing.md) | Unit/contract/golden/scenario testing layers for skill behavior, especially executable or high-risk routes |
| [conventions.md](references/conventions.md) | Common rule file sets by project type, decision guide, what to preserve vs remove, anti-patterns, troubleshooting, file size guidelines, naming conventions, optional CI validation |
| [self-hosting-routing.yaml](references/self-hosting-routing.yaml) | Canonical YAML route manifest for this repo's root thin-shell bootstraps, plus sync/check protocol |
| [self-hosting-conformance.yaml](references/self-hosting-conformance.yaml) | Content-presence guard for this repo's own canon — asserts canonical files still teach the protocols `templates/skill/conformance.yaml` promises downstream |

New references should link to the topic file directly (e.g. `references/per-tool-shells.md#tool-compatibility-summary`), not through this stub.
