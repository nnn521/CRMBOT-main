# Scenario Testing for Skills

Structural checks prove the skill is shaped correctly. Scenario tests prove the
agent is likely to do the right thing for a real user request.

## Test Layers

Use only the layers justified by the skill's risk:

| Layer | Proves | Add when |
|---|---|---|
| Unit | Script functions handle parsing, config, and formatting | `scripts/` contains reusable logic |
| Contract | Docs, indexes, constants, and error registries stay synchronized | The skill has generated indexes, error codes, API paths, or output contracts |
| Golden | CLI output stays stable for callers | Workflows depend on exact script stdout shape |
| Scenario | User language routes to the expected reads, calls, and final behavior | A route is high-risk, ambiguous, side-effectful, or expensive to get wrong |

Rule-only skills often need only structural and contract checks. Executable
skills usually need all four layers for their highest-risk routes.

## Contract Test Patterns

Good contract tests are deterministic and harness-neutral:

- Directory index consistency: every file in `tools/`, `capability/`, or
  `workflows/` appears in the matching `INDEX.md`, and every index entry points
  to a real file.
- Error code registry: every `ERR_*` referenced by capability or workflow docs
  is defined in the central error file.
- Script constant consistency: every documented external path, command name, or
  schema key is registered in the script constants it depends on.
- Routing target existence: every route target points to an existing workflow,
  reference, rule, or external skill invocation note.

Keep these tests local and cheap so they can run before commit.

## Scenario Test Pattern

A scenario test should be a small transcript-shaped proof:

1. Provide one realistic user prompt in the language users actually use.
2. Run the agent or a route simulator in an isolated workspace.
3. Stub external calls so no real remote side effects occur.
4. Record actual reads, commands, or mocked API calls.
5. Assert a loose subset: required files were read, expected calls occurred,
   forbidden calls did not occur, and the final answer used the mocked result.

Prefer subset assertions over exact transcript matching. Agents can legitimately
change wording or intermediate order while preserving behavior.

This upstream repo keeps only minimal self-hosting route proofs in
`scripts/check-self-scenarios.sh`. That script is intentionally not copied as a
default downstream harness; downstream projects add their own scenario tests
only for routes with real behavior risk.

## When To Add Scenario Tests

Add a scenario test when one of these is true:

- The route performs or prepares a non-idempotent action.
- The user wording overlaps multiple routes and a wrong choice is costly.
- A previous behavior failure came from route selection rather than missing
  files.
- A workflow depends on external skill invocation or mocked external systems.
- A route has custom slot-filling or confirmation logic.

Do not ship a heavy scenario harness in the default template. Start with this
reference and add project-owned tests only when the project has real behavior to
protect.
