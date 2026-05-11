# /reviewslop — Slop Review Command

Run the slop-reviewer sub-agent against the current repo and write the findings to SLOP_AUDIT.md.

## Usage
```
/reviewslop
```

## What it does
1. Delegates to the `slop-reviewer` sub-agent defined at `.claude/agents/slop-reviewer.md`.
2. The agent reads `SPEC.md` as the source of truth.
3. It walks every file in the repo and classifies each entity as REQUIRED, SUPPORTING, or SLOP.
4. It writes the full classification table + evidence + cleanup diff to `SLOP_AUDIT.md`.

## When to run
- After any new feature or dependency is added.
- Before submitting / pushing to GitHub.
- Any time a reviewer would question why a file, function, or import exists.
