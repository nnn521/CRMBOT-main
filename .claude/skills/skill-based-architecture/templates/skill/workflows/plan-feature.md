# Plan Feature Workflow

Use this for planning requests. Only complex plans get a `docs/plans/.../` folder; simple plans stay inline in the conversation unless the user explicitly asks for a file.

## Complexity Gate

| Size | Signal | Action |
|---|---|---|
| Trivial | typo, comment, obvious one-line change | skip this workflow |
| Simple | clear goal, 1-2 files, no product ambiguity | ask at most one confirmation question; no folder |
| Complex | multiple files, unclear behavior, external dependency, architecture choice, or long run | create a dossier folder and continue below |

## Question Gate

Before asking any question, pass all three gates:
1. **Gate A: Derivable?** If code, docs, configs, tests, issue text, or quick primary-source research can answer it, inspect first. Do not ask.
2. **Gate B: Meta / lazy?** Never ask "should I search?", "can you paste the code?", or "what does this repo look like?" when the repo or source is available. Take the action.
3. **Gate C: Blocking / Preference / Derivable?** Ask only `Blocking` or `Preference` questions. Resolve `Derivable` questions yourself and record evidence.

Ask one question at a time. Prefer 2-3 concrete options with trade-offs for preference questions.

## Simple Plan

For Simple tasks, do not create `docs/plans/` and do not write `.skill-workflow-state`. Produce a short inline plan with scope, steps, and validation. If one confirmation is needed, ask it before writing the plan.

## Complex Task Dossier

For Complex tasks, create one directory:

```text
docs/plans/YYYY-MM-DD-<slug>/
├── prd.md
├── decisions.md
├── checklist.md
├── research/
├── evidence/
├── implement.jsonl
└── check.jsonl
```

Keep `prd.md` short: goal, scope, requirements, acceptance criteria, out of scope, and current open questions. Put supporting material elsewhere:

- `decisions.md` — ADR-lite entries with `Context`, `Decision`, and `Consequences`.
- `research/` — summarized research findings.
- `evidence/` — copied source/doc snippets with file path and line references.
- `implement.jsonl` — files the implementer must read first.
- `check.jsonl` — files the checker/reviewer must read first.

JSONL row shape: `{"file":"docs/plans/YYYY-MM-DD-<slug>/prd.md","reason":"Accepted scope"}`.

## Complex State File

For Complex tasks only, write `.skill-workflow-state` if the optional workflow-state hook is installed:

```text
workflow=skills/{{NAME}}/workflows/plan-feature.md
status=planning
task=docs/plans/YYYY-MM-DD-<slug>
```

Update `status` as the task moves. Delete the file when the plan is complete or the workflow is abandoned.

## Complex Steps

1. **Create / update dossier** — create the directory and seed `prd.md`, `decisions.md`, `checklist.md`, `research/`, `evidence/`, `implement.jsonl`, and `check.jsonl`.
2. **Inspect first** — gather repo evidence before questioning: similar features, entry points, config, scripts, tests, and current docs.
3. **Question gate** — classify each possible question through Gate A/B/C; ask only the highest-value next question.
4. **Define scope** — write requirements, acceptance criteria, and out-of-scope items in `prd.md`.
5. **Record decisions** — when choosing between approaches, append ADR-lite entries to `decisions.md`.
6. **Prepare execution context** — fill `implement.jsonl` and `check.jsonl` with only relevant rule, workflow, research, evidence, and PRD files.
7. **Final readback** — summarize requirements, acceptance criteria, chosen approach, out-of-scope items, and dossier path.

## Workflow-State Blocks

[workflow-state:planning]
You are planning a complex task. Keep `prd.md` short, inspect code/docs before asking, and run Question Gate A/B/C before every user question.
[/workflow-state:planning]

[workflow-state:research]
External or cross-repo research is active. Put summaries in `research/`, put quoted source/doc snippets with file:line references in `evidence/`, and avoid unsupported paraphrase.
[/workflow-state:research]

[workflow-state:converging]
Requirements are being locked. Move answered questions into `prd.md`, record trade-offs in `decisions.md`, and keep out-of-scope explicit.
[/workflow-state:converging]

[workflow-state:implementation-ready]
Planning is complete. Verify `implement.jsonl` and `check.jsonl` point at the PRD, rules, decisions, and any research/evidence needed before implementation starts.
[/workflow-state:implementation-ready]

## Completion Checklist

- [ ] Trivial/simple tasks were not forced into a dossier
- [ ] Simple plans stayed inline unless the user explicitly asked for a file
- [ ] Every asked question passed Gate A/B/C
- [ ] `prd.md` contains testable acceptance criteria
- [ ] `decisions.md` records approach trade-offs when choices mattered
- [ ] Research and evidence are not mixed into `prd.md`
- [ ] `implement.jsonl` and `check.jsonl` contain only relevant files
- [ ] `.skill-workflow-state` was removed or left with the correct active state
