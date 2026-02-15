# DESIGN_PRINCIPLES.md - Architectural Standards

This document defines the core engineering philosophy and architectural constraints of the project. These principles are abstract and apply regardless of specific technology or module names.

## 1. Layered isolation
- **Ingress layer**: Responsible solely for protocol handling (e.g., HTTP, CLI). It must not contain business logic or direct tool execution.
- **Logic layer**: Manages flow, sequence, and state. It coordinates "Thinking" (Decision) and "Acting" (Execution).
- **Execution layer**: Atomic, functional components (Tools). Each must be independent and side-effect free relative to others.

## 2. SOLID behavioral rules
- **Behavioral SRP**: Each component represents a single atomic action. Compound behaviors must be decomposed.
- **Contract stability**: Boundary-crossing data must use strictly defined schemas (e.g., Pydantic). No raw dictionaries or lists should be exchanged between layers.
- **Extension by addition**: Extend system capability by adding new atomic components, not by modifying existing logic flows.

## 3. State integrity
- **Unidirectional flow**: Application state moves in a single, predictable direction. Every transition must be traceable.
- **State immudability (Patches)**: Components should not modify state directly. They provide "patches" or "deltas" to be applied by the logic engine.

## 4. Robust execution
- **Observation over exception**: Logical failures (e.g., tool errors) are treated as data to be processed by the logic layer.
- **Infrastructure integrity**: Only infrastructure failures (e.g., DB down, Network lost) should trigger catastrophic exceptions (Fail-Fast).

## 5. Dependency injection
- **Components receive dependencies, they don't import globals.** Core collaborators (graph, LLM, config) are passed via constructors or framework-level injection (e.g., FastAPI `Depends()`).
- **Single wiring point**: All dependency construction and assembly happens in one dedicated location (e.g., a `dependencies` module), not scattered across consumers.
- **Testability by design**: Any component can be tested by substituting its dependencies — no `patch()` of deep import paths required.

## 6. Single config source
- **All configuration flows through `Settings`.** No direct `os.getenv()` calls in business or tool code.
- **One truth, one path**: Environment variables are loaded once by the settings layer. Downstream code reads from the `settings` singleton only.

## 7. No dead code
- **No orphan modules**: Superseded or unused files are removed, not left alongside active code.
- **No phantom state**: Unused fields in state models (e.g., agent state) are pruned. Every field must be read and written by at least one active code path.

## 8. Testable Architecture
- **Centralized Testing**: Tests reside in a dedicated `tests/` directory, mirroring the source structure. This ensures clean separation of concerns and prevents test code from leaking into production builds.
- **Coverage as a Metric**: High test coverage (>80%) is a requirement, not a bonus. It serves as a safety net for refactoring and a quality gate for new features.
- **Mock Externalities**: All external I/O (APIs, Databases, LLMs) must be mocked in unit tests to ensure deterministic execution. Integration tests may hit real services but must be explicitly marked.
