# Lessons Learned

A curated collection of **surprising, important, hard-won insights** discovered while building `iso-topos`.

> **Decision Diary vs. Lessons Learned:** Use [`decisions/DECISIONS.md`](../decisions/DECISIONS.md) for intentional architectural/scientific choices. Use this folder for *things that surprised you and matter for future work* (dataset quirks, coordinate/unit traps, library gotchas, failed assumptions).

## How to Add a Lesson
1. Create a file named `YYYY-MM-DD-<short-slug>.md` in this directory using the template below.
2. Add a row to the **Index** table in this file.
3. Keep each note focused, concrete, and actionable—skip trivial typos or routine debugging.

## Lesson Template

```markdown
# <Concise Lesson Title>

- **Date:** YYYY-MM-DD
- **Area / Tags:** e.g., `etl`, `lunar-data`, `coordinates`, `scoring`, `frontend`

## What Surprised Us
Describe the unexpected behavior, dataset quirk, or broken assumption.

## Why It Matters
Explain the impact (e.g., silent scientific inaccuracy, broken map alignment, wasted time).

## Rule of Thumb / What To Do Instead
State the concrete check, invariant, or pattern to follow going forward.

## References
- Links to affected code, datasets, tests, or `DEC-XXX` entries.
```

---

## Index

| Date | Lesson | Area / Tags | Summary |
| :--- | :--- | :--- | :--- |
| *(none yet)* | | | |
