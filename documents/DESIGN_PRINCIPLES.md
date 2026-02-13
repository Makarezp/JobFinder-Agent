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
