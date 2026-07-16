# Agent Conversation Documentation Rules

## Goal

Solve engineering work through normal conversation, then merge verified knowledge into two living documents:

- `SPEC.md`: how the system runs, is implemented, and is troubleshot.
- `SYSTEM.md`: what users can do and which business rules apply.

Documentation is an output of completed work. Do not ask the user to fill formal requirement, design, test, or release templates before starting.

## Route Every Engineering Request

Ask one question:

> Should the system already do this?

| Route | Use when |
|-------|----------|
| `problem` | Existing behavior is unavailable, broken, or producing errors |
| `scenario` | A new or changed user capability is requested |
| `clarify` | One missing answer would change the route |

For `clarify`, ask only the blocking question. Status questions and explanations that do not create engineering work are answered directly without creating a task card.

## Acceptance Confirmation Gate

Every new engineering request must pass this gate before implementation:

1. Understand the user's intent and classify the route.
2. Inspect relevant project context with read-only actions when needed.
3. Derive the smallest complete set of observable acceptance scenarios.
4. Present the intent summary and acceptance scenarios to the user.
5. Wait for an explicit `approve`, `edit`, or `reject` decision.
6. Start implementation only after approval.

The Agent derives acceptance scenarios from the request, existing behavior, code, and project documents. Never require the user to write them. If the request already contains acceptance conditions, normalize and present them for confirmation anyway.

Before approval, do not modify files, execute state-changing commands, or perform external actions. Silence and an earlier instruction to "go ahead" are not approval of scenarios that the Agent has not presented yet.

Follow-up evidence or answers within an approved task do not restart the gate. If a later message changes the goal, scope, or expected outcome, revise the affected scenarios and request approval again.

## Working Record

For active engineering work, create one card in `plan.md`. The Agent derives the card from the conversation; the user does not fill it manually.

```markdown
[ID][problem|scenario] Title

Goal or symptom:
Acceptance scenarios:
Acceptance confirmed:
Result:
Documents:
Related files or commit:
```

Create or move the card to In Progress only after acceptance is confirmed. Move it to Done only after every accepted scenario has been verified.

## Problem Flow

```text
Symptom → Understand → Confirm acceptance → Reproduce → Diagnose → Fix → Verify → Update SPEC.md
```

1. Inspect the real runtime, logs, configuration, dependencies, and relevant code.
2. Separate confirmed evidence from hypotheses.
3. Fix the root cause when the user requested a change.
4. Run the smallest check that proves the problem is resolved.
5. Merge reusable facts into `SPEC.md`.

Record stable startup commands, configuration constraints, architecture facts, root causes, repairs, and verification steps. Do not copy raw logs or failed guesses into the living document.

## Scenario Flow

```text
User goal → Understand → Confirm acceptance → Implement → Verify → Update SYSTEM.md
```

1. Identify the user, goal, current behavior, and observable completion criteria from the conversation and codebase.
2. Ask only for information that cannot be discovered and would materially change the result.
3. Implement the smallest complete solution.
4. Verify the user-visible behavior.
5. Merge the confirmed capability into `SYSTEM.md`.
6. Also update `SPEC.md` only when a reusable technical contract changed.

## Living Document Rules

1. Write only verified current facts.
2. Merge with the relevant section instead of appending a task report.
3. Replace statements that are no longer true; Git preserves history.
4. Keep temporary investigation notes in the conversation or active task card.
5. Link completed cards to the updated document section and relevant commit.
6. Never record secrets, tokens, personal data, or credentials.

## Human Approval

Pause for approval before destructive operations, production deployment, rollback, security-sensitive changes, or any action whose scope materially exceeds the user's request.
