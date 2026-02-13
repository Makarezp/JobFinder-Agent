> [!NOTE]
> **HISTORICAL DOCUMENT**: This file captures the original vision and ideation.
> For active Business Rules, Glossary, and Project Status, please refer to **[domain.md](domain.md)** and **[README.md](../README.md)**.

# Project Vision: The "Tinder for Jobs" Agent

## The Core Concept
An **Agentic AI Companion for Job Seekers** that doesn't just list jobs, but *learns* what you want. It evolves from a simple search tool into a personalized headhunter that knows your taste better than you do.

## Target Audience
**Technical Professionals & Developers** (Contractors & Perm).
- They have specific, nuanced requirements (tech stack, culture, salary, remote work).
- They are tired of generic job boards and keyword-mashing recruiters.

## Key Problems to Solve
1. **Noise**: Listings are often irrelevant even if they match keywords.
2. **Time**: Reviewing mismatched jobs is a waste of life.
3. **Context**: Standard filters don't capture "vibe" or specific preferences (e.g., "I only want startups" or "No legacy code").

## The "Magic" Moment
The user uploads their CV, and the Agent immediately says: *"Based on your experience with Python and recent focus on AI, here are 3 hidden gem roles. This one is perfect because..."*
Then, as the user swipes "No" on a corporate job, the Agent asks *"Too bureaucratic?"*, learns, and never shows that type again.

## Core Features (The "Dream" Flow)
1. **CV Onboarding**: Agent analyzes the user's CV to establish a baseline profile.
2. **The "Tinder" Interface**:
    - **Swipe Right**: "I'm interested." -> Agent prepares summary & apply link.
    - **Swipe Left**: "Not for me." -> Agent asks *why* (Feedback Loop).
3. **Continuous Learning**: The Agent builds a dynamic internal profile of the user's preferences based on every interaction.
4. **Rationale Engine**: Every job proposal comes with a specialized "Pitch": *"I picked this because you said you wanted a smaller team and Go-lang."*
5. **Long-term Memory**: The Agent remembers every job it has ever shown you.
    - **No Duplicates**: Never proposes the same job twice unless explicitly asked.
    - **Evolution**: "You rejected a similar role 3 weeks ago, so I'm skipping this one."

## Engineering Principles (The "How")
- **Agent-First**: The core value is the background agent, not the UI.
- **No Frontend Ops**: Use HTMX for investigating the agent's brain. No React/Next.js for now.
- **Production Quality**: Code should be clean, typed, and tested. Shortcuts allowed on *infrastructure* (e.g., SQLite vs Postgres), but not on *code quality*.
- **Limited Scope**: Start with Adzuna only to prove the agent's reliability.
- **Headless Capable**: The system must run on a cron/background schedule, not just request-response.

## Phased Rollout
### Phase 1: The Interactive Headhunter (Current Focus)
- **Goal**: Conversational Agent that understands criteria and scouts on demand.
- **Features**:
    - Chat Interface (simple HTMX).
    - Natural Language understanding of job preferences.
    - Real-time searching using Adzuna Tool.
    - Agent feedback ("This isn't what I meant").

### Phase 2: The Reliable Scout & Memory
- **Goal**: Autonomous background search & long-term memory.
- **Features**:
    - SQLite persistence ("Seen Jobs").
    - Cron-triggerable search cycle.
    - Deduplication logic.



## Current Assets (Context)
- Reviewing the existing codebase (`CVviewer`) suggests a focus on:
    - **Job Search**: Tools for Adzuna (job board).
    - **AI Agents**: LangGraph implementation.
    - **Scraping**: Capability to read web pages.

## Open Questions
- **Interaction Depth**: Is it purely swiping, or can we chat with it like a recruiter? ("Find me something weird today.")
- **Data Sources**: Where are we hunting? (Adzuna is a start, but tech jobs are often on niche boards or LinkedIn).
