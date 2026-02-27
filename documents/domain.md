# domain.md - Knowledge Base

## 1. Glossary
- **JSearch**: The RapidAPI-based job search aggregator used for real-time job discovery. Returns rich job data (title, company, location, salary, description) in a single API call.
- **LangGraph**: The framework managing our Agent's state machine (cyclic execution).
- **Nodes**: Logical steps in the Agent's graph (e.g., `chatbot`, `tools`).

## 2. Business Rules
- **Skill Priority**: When searching, **ALWAYS** prioritize skills found in the user's `cv_text` over generic job titles.
- **Description Truncation**: JSearch returns full job descriptions directly. These are truncated to 1,000 characters before being added to the agent state to protect the LLM context window. The agent must evaluate fit based on this snippet and not penalise a job for appearing incomplete.
- **Remote Work**: To find remote jobs, set `remote_only=True` in the `job_specialist_tool` call.

## 3. Project Vision
"The Tinder for Jobs"
- **Personalized**: It doesn't just match keywords; it learns preferences (e.g., "No corporate vibes").
- **Evolving**: The agent remembers what you disliked and refines future searches.
