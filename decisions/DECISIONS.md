# Decision Diary

A chronological log of important architectural, scientific, dataset, tooling, and scope decisions for `iso-topos` (`ER-3` in [REQUIREMENTS.md](../REQUIREMENTS.md)).

## How to Use This File
- **Read before acting:** Check existing decisions before proposing conflicting tech, schemas, or scoring changes.
- **Append-only:** Never delete or rewrite history. To change a past decision, add a new `DEC-XXX` entry and update the superseded entry's `Status` to `Superseded by DEC-YYY`.
- **What belongs here:** Tech stack choices, module/API boundaries, spatial index resolution, dataset selections, unit/scoring math, and deliberate scope trade-offs. Routine bug fixes do not belong here.

## Entry Template

```markdown
## DEC-XXX: <Short Title>
- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by DEC-YYY
- **Context:** What problem or requirement forced a choice?
- **Options Considered:**
  1. Option A — pros / cons
  2. Option B — pros / cons
- **Decision:** What was chosen and why.
- **Consequences:** Downstream impacts, constraints, or follow-up work created.
- **Related:** Links to files, requirements (`FR-*`/`DR-*`/`ER-*`), or lessons learned.
```

---

## Decisions

*(No decisions recorded yet. Add `DEC-001` below when the first architectural, dataset, or stack decision is made.)*
