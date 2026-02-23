# PERSONAS.md - AI Agent Context Manual

This document defines the roles and required documentation context for AI agents working on the CVviewer project. When assigned a persona, you MUST read the specified files to ensure alignment and prevent context pollution.

## 🏗️ Architect
**Purpose**: High-level system design, architectural constraints, and structural changes.
- **Read List**:
  - [README.md](../README.md)
  - [domain.md](domain.md)
  - [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)
  - [ideation.md](ideation.md)

## 👨‍💻 Senior Developer
**Purpose**: Feature implementation, component building, and API development.
- **Read List**:
  - [README.md](../README.md)
  - [domain.md](domain.md)
  - [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)
  - [CONVENTIONS.md](CONVENTIONS.md)
  - [AGENTS.md](AGENTS.md)
  - [Active Sprint Ticket](../work_organisation/sprints/) (Ask for specific file)

## 🐛 Senior Developer - Bug Fixer
**Purpose**: Debugging, troubleshooting, and solving technical debt.
- **Read List**:
  - [README.md](../README.md)
  - [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)
  - [CONVENTIONS.md](CONVENTIONS.md)
  - [AGENTS.md](AGENTS.md)
  - [bug_tracker.md](../work_organisation/bugs/bug_tracker.md)

## 💡 Product Ideator
**Purpose**: Evolving product vision, brainstorming features, and UX strategy.
- **Read List**:
  - [README.md](../README.md)
  - [ideation.md](ideation.md)
  - [domain.md](domain.md)

## 🧪 QA / Tester
**Purpose**: Test execution, coverage auditing, and code quality verification.
- **Read List**:
  - [README.md](../README.md)
  - [CONVENTIONS.md](CONVENTIONS.md) (Testing & Logging)
  - [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) (Testable Architecture)

---

## 🚫 Critical Rules for All Personas
- **work_organisation/history/**: **DO NOT READ** unless explicitly requested by the user for a specific file. This avoids "poisoning" your context with legacy designs.
- **Context Targeted**: Only read what is necessary for your persona to preserve token efficiency and focus.
