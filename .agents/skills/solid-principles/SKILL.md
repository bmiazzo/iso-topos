---
name: solid-principles
description: >-
  Pragmatic SOLID design, implementation, and refactoring workflow for agents.
  Use when designing new modules or classes, writing non-trivial application or
  data-pipeline code, or reviewing and refactoring existing code for
  maintainability and clean boundaries.
---

# SOLID Principles Workflow

Apply the five SOLID principles pragmatically to keep modules cohesive, extensible, and easy to test without introducing premature abstractions.

## Quick Reference & Guardrails

| Principle | Core Question | Warning Smell | Pragmatic Guardrail |
| :--- | :--- | :--- | :--- |
| **S — Single Responsibility** | Does this unit have one reason to change? | "God" classes/modules mixing I/O, business logic, and formatting | Split by *axis of change* (e.g., data fetching vs. domain logic), not into tiny 1-method wrappers |
| **O — Open/Closed** | Can we add a new variant without editing core branching logic? | Growing `if/elif` or `switch` chains on type/kind | Wait for 2–3 real variants (Rule of Three) before extracting a strategy/registry |
| **L — Liskov Substitution** | Can any subtype/implementation replace the base without surprises? | Subclass throws `NotImplementedError`, narrows inputs, or breaks invariants | Prefer composition or smaller interfaces over forcing awkward inheritance |
| **I — Interface Segregation** | Are callers forced to depend on methods/fields they don't use? | Fat interfaces/protocols where implementers stub out unused methods | Define small, role-specific interfaces at the consumer boundary |
| **D — Dependency Inversion** | Does high-level policy depend on abstractions rather than concrete I/O? | Domain logic directly instantiating HTTP clients, DBs, or filesystem paths | Inject I/O boundaries (functions, protocols, clients) at the composition root |

---

## Mode 1: Designing & Writing New Code

Follow these steps when creating new modules, services, or pipelines:

1. **Identify Axes of Change**: Separate pure domain/computation logic from external I/O (APIs, files, databases, UI rendering).
2. **Keep Boundaries Thin**: Define minimal contracts (Python `Protocol`/callable or TypeScript `interface`/type) at the *consumer* side only when multiple implementations or testability require a seam.
3. **Favor Composition**: Assemble behavior from small, focused functions or objects rather than deep inheritance hierarchies.
4. **Silent Self-Check**: Before finishing, verify against the Quick Reference table above. Do **not** output a SOLID report unless the user asked for a review—just ensure the code is clean and well-factored.

---

## Mode 2: Reviewing & Refactoring Existing Code

Follow these steps when auditing or refactoring code:

1. **Locate Smells**: Inspect target files for mixed responsibilities, rigid `if/switch` dispatch, broken subtype contracts, fat interfaces, or hardcoded I/O dependencies.
   - For detailed smell catalogs and refactoring moves, read [Principles and Smells](./references/principles-and-smells.md).
   - For idiomatic Python and TypeScript/JS patterns, read [Python & TypeScript Patterns](./references/python-typescript-patterns.md).
2. **Present a Structured Audit**: Report findings using a concise table:

   | Principle | Location & Smell | Concrete Fix |
   | :--- | :--- | :--- |
   | e.g. **SRP** | `file.py:L20-L95` mixes CSV parsing, scoring, and plotting | Extract `parse_records()` and `plot_scores()` helpers |

3. **Refactor Incrementally**:
   - Apply one boundary/responsibility extraction at a time.
   - Preserve existing public behavior unless a bug or contract violation is being fixed.
4. **Verify**:
   - Run the project's test suite, type checker, or linter (e.g., `pytest`, `mypy`/`pyright`, `tsc`, `npm test`) after refactoring to confirm behavior is intact and no interfaces were broken.
