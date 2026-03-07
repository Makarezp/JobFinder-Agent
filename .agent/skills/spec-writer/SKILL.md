---
name: Technical Specification Architect (Spec Writer)
description: Synthesizes conversation history and codebase context into a structured Markdown specification file and save it to the project documentation.
---

# SKILL: GENERATE SPECIFICATION

## 1.0 CONTEXT & OBJECTIVE
You are acting as a **Technical Specification Architect**.
**Trigger:** The user has finished ideating/discussing a feature or task with you.
**Goal:** Synthesize the conversation history and current codebase context into a structured Markdown specification file and save it to the project documentation.

## 2.0 FILE PLACEMENT RULES
*   **Target Directory:** `work_organisation/spec/`
*   **Directory Creation:** If this directory does not exist, you must create it.
*   **Filename Convention:** Use a kebab-case slug based on the feature name (e.g., `user-auth-refactor.md` or `api-rate-limiting.md`).

## 3.0 CONTENT GENERATION PROCESS

### 3.1 Synthesis
1.  **Analyze Chat History:** Extract the core requirements, constraints, and goals we discussed.
2.  **Analyze Codebase:** Cross-reference our discussion with existing files to ensure technical accuracy (e.g., correct file paths, variable names, and architectural patterns).

### 3.2 Document Structure
The generated Markdown file MUST follow this template:

```markdown
# Specification: [Feature/Task Name]

## 1. Overview
*   **Summary:** A concise description of what is being built/changed.
*   **Context:** Why are we doing this? (Derived from chat history).

## 2. Functional Requirements
*   [ ] Requirement 1
*   [ ] Requirement 2
*   ...

## 3. Verification & Acceptance Criteria
*   [ ] Condition A (e.g., "User receives 403 on invalid token")
*   [ ] Condition B
*   ...
```
