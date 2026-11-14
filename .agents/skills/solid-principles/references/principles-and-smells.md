# SOLID Principles: Smells, Refactoring Moves, and Guardrails

## 1. Single Responsibility Principle (SRP)
*A module, class, or function should have one, and only one, reason to change.*

- **Common Smells**:
  - A class or script fetches data from an API, transforms it, computes metrics, and writes HTML/charts all in one function or class.
  - Files with unrelated utility functions dumped together (`utils.py`, `helpers.ts`).
  - Changes to output formatting force edits to core calculation code.
- **Refactoring Moves**:
  - Extract cohesive units by *layer or responsibility*: ingestion/I/O, domain transformation, and presentation/serialization.
  - Keep orchestration ("glue") separate from computation.
- **When NOT to split**:
  - Do not split a 20-line cohesive function into three single-use classes. Cohesion matters as much as separation.

## 2. Open/Closed Principle (OCP)
*Software entities should be open for extension, but closed for modification.*

- **Common Smells**:
  - Repeated `if kind == "A": ... elif kind == "B": ...` or `switch` statements scattered across multiple functions.
  - Adding a new data source, export format, or similarity metric requires editing core pipeline logic.
- **Refactoring Moves**:
  - Replace type-code branching with a **Strategy** (callable/protocol/interface) or a **Registry/Mapping** (`dict[str, Handler]` or `Record<string, Handler>`).
- **When NOT to abstract**:
  - If there is only 1 implementation (or 2 trivial ones that never change), a simple conditional is clearer than a plugin architecture. Apply OCP when a second/third variant actually arrives or is explicitly planned.

## 3. Liskov Substitution Principle (LSP)
*Subtypes must be substitutable for their base types without altering correctness.*

- **Common Smells**:
  - A subclass overrides a method to throw `NotImplementedError` / `UnsupportedOperationError` or silently no-ops.
  - Callers use `isinstance(x, Subclass)` / `x instanceof Subclass` to handle special cases.
  - A subtype strengthens preconditions (rejects inputs the base accepts) or weakens postconditions (returns `None` when base promises a value).
- **Refactoring Moves**:
  - Replace inheritance with **composition** or **capability-based interfaces** (see ISP).
  - Model shared behavior via small, explicit contracts rather than a broad base class.

## 4. Interface Segregation Principle (ISP)
*Clients should not be forced to depend on interfaces they do not use.*

- **Common Smells**:
  - Large `DataProvider` or `Service` interfaces with 10+ methods where most callers only need 1 or 2.
  - Test mocks requiring dozens of dummy/stubbed methods just to test one function.
- **Refactoring Moves**:
  - Split fat interfaces into small, role-based contracts (e.g., `Reader` and `Writer` instead of `Repository`).
  - In Python, use `typing.Protocol` with only the methods the consumer calls. In TypeScript, accept structural types like `Pick<T, ...>` or focused interfaces.

## 5. Dependency Inversion Principle (DIP)
*High-level policy should not depend on low-level details; both should depend on abstractions.*

- **Common Smells**:
  - Domain or analysis functions directly calling `requests.get()`, `open()`, `os.environ`, or `fetch()` inside business logic.
  - Hardcoded concrete clients instantiated inside constructors (`self.db = PostgresClient()`).
- **Refactoring Moves**:
  - Accept dependencies (clients, readers, clocks, loggers, or pure callback functions) as parameters.
  - Wire concrete implementations together at the **composition root** (e.g., `main.py`, CLI entrypoint, or app factory).
- **When NOT to abstract**:
  - Standard library pure utilities (math, string/date formatting, immutable data structures) do not need interfaces wrapped around them.
