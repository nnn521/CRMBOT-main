# Executable Skill Architecture

Use this reference when a project skill must operate external systems, not only
describe project rules. The default scaffold stays rule-oriented; this is an
upgrade path for operation-heavy skills.

Executable is an execution-mode axis, not a full shape replacement. Decide it
separately from structure tier (Single-file / Folder-light / Full) and domain
topology (Single-skill / Multi-skill candidate).

## When To Use

Adopt the executable shape only when at least two pressures are present:

- The skill calls external APIs, CLIs, databases, cloud services, or remote
  platforms as part of normal user tasks.
- The skill needs deterministic scripts because agents would otherwise rewrite
  fragile shell or HTTP logic repeatedly.
- Tasks have side effects such as deploys, writes, status transitions, or remote
  configuration updates.
- Callers need stable output contracts that hide raw API response shapes.
- Users need local, non-committed configuration such as API keys, base URLs,
  product codes, auth headers, or runtime paths.

If the project mostly records coding conventions, review rules, or recurring
procedures, stay with the normal `rules/`, `workflows/`, and `references/`
layout.

## Recommended Shape

```text
skills/<name>/
├── SKILL.md
├── conf/
│   └── .defaults/
├── scripts/
├── tools/
├── capability/
├── workflows/
├── references/
└── rules/
```

Responsibilities:

| Layer | Owns | Avoids |
|---|---|---|
| `scripts/` | How to execute: auth, HTTP, CLI wrappers, config loading, parsing | Business routing and user-facing prose |
| `tools/` | One atomic external operation: method/path/params/return/error/idempotency | Business triggers, fallback policy, multi-step flow |
| `capability/` | One domain business ability with a stable output contract | Cross-domain orchestration, user-environment side effects |
| `workflows/` | Full user intent, multi-step flow, confirmations, side effects | Repeating capability internals inline |
| `conf/.defaults/` | Copyable user-local config templates | Real secrets or project-owned runtime instances |

Dependency direction should stay one-way:

```text
workflows -> capability -> tools -> scripts
```

`scripts/` may also be called directly by workflows when the script is pure
execution infrastructure, such as project introspection or runtime argument
assembly.

## Contracts

Executable skills need contracts earlier than rule-only skills:

- Every `tool` declares idempotency and the exact input shape.
- Every `capability` declares a stable output contract; callers do not depend on
  raw tool fields.
- Every non-idempotent workflow has a confirmation point immediately before the
  side effect.
- Every local config value has a source order and a safe missing-value behavior.
- Every large or noisy external response has a way to inspect targeted fields
  without loading the whole payload into context.

## What Not To Promote

Do not create an executable skill because the structure looks more complete.
Do not add `tools/`, `capability/`, `scripts/`, or `conf/` to the default
template. Two ordinary projects should be able to adopt the base scaffold
without inheriting operation-specific directories they do not use.

Promote this shape only from project evidence gathered by
`workflows/profile-project.md`: external execution surface, side effects,
stable output contracts, local configuration, or repeated script logic.

## Validation

Minimum validation for executable skills:

- Structural checks still pass: routing sync, link checks, orphan checks.
- Contract checks cover index-to-file consistency and registered error codes.
- Script tests cover pure parsing/config logic.
- Golden tests cover CLI output that other workflows depend on.
- Scenario tests cover high-risk user intent routes when route correctness
  matters more than file shape.
