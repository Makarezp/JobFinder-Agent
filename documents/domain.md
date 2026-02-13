# domain.md - Knowledge Base

## 1. Glossary
- **Adzuna**: The primary job aggregation platform we use.
- **Crawl4AI**: Our headless browser engine for scraping details from job pages.
- **LangGraph**: The framework managing our Agent's state machine (cyclic execution).
- **Nodes**: Logical steps in the Agent's graph (e.g., `chatbot`, `tools`).

## 2. Business Rules
- **Skill Priority**: When searching, **ALWAYS** prioritize skills found in the user's `cv_text` over generic job titles.
- **Deep Scraping**:
    - Search results give summaries.
    - To get full details (salary, benefits), the Agent **MUST** use `scrape_website` on the "Apply Here" link.
    - **Limit**: Scrape max 3 top jobs to save time/bandwidth.
- **Remote Work**: To find remote jobs on Adzuna, append "remote" to the keywords (the API/scraper handles the specific parameter logic).

## 3. Project Vision
"The Tinder for Jobs"
- **Personalized**: It doesn't just match keywords; it learns preferences (e.g., "No corporate vibes").
- **Evolving**: The agent remembers what you disliked and refines future searches.
