# JSearch API Analysis and Recommendations

## Issue Overview
The Job Specialist Agent is failing to find relevant non-US jobs (such as UK-based and European jobs), leading to repeated empty results and triggering a "max search attempts reached" loop.

Based on extensive testing using the JSearch RapidAPI directly with various parameter combinations, the failures stem from two fundamental issues in how we query the API:

### 1. The Missing `country` Parameter
**Finding**: JSearch defaults to finding jobs in the US (`country=us`).
When searching for a job in a non-US city (e.g., "Android Developer London" or "Android Developer Berlin"), the query alone is often ignored or overridden by the default US country parameter, resulting in zero matching results.
**Test Results**:
- `query="Android Developer contract London"` -> **0 results**
- `query="Android Developer contract London"`, `country="gb"` -> **10 results**
- `query="Android Developer Berlin"`, `country="de"` -> **10 results**

**Recommendation**: We have added the `country` parameter as a **MANDATORY** field in the `JobSpecialistInput` schema. This forces the LLM to explicitly populate the 2-letter ISO country code for every search, preventing the default US-centric bias of the JSearch API.

### 2. The Unreliable `employment_types` Filter for Non-US Jobs
**Finding**: Applying the `employment_types=CONTRACTOR` filter parameter causes valid search queries in locations like the UK to return **0 results**. Google for Jobs (which powers JSearch) frequently fails to tag non-US contract roles with exactly this internal flag.
**Test Results**:
- `query="Android Developer London"`, `country="gb"`, `employment_types="CONTRACTOR"` -> **0 results**
- `query="Android Developer contract London"`, `country="gb"` (without `employment_types`) -> **10 results**, almost all of which are contract roles.

**Recommendation**: The `employment_types` parameter is too brittle, especially outside the US. Instead, if a user wants a "contract" or "remote" job, it is significantly more reliable to instruct the LLM to simply include these keywords in the free-form `query` text (e.g., "Android Developer remote contract London"). We should consider deprecating or removing `employment_types` from the agent UI and instead rely on prompt-engineering the agent to inject these words into the title string.

## Implemented Changes
1. **Mandatory Country Parameter**: Added `country` to `JobSpecialistInput` (no default) and exposed it in the `jsearch_api_search` tool.
2. **Propagated country parameter**: updated the `search_jobs` node to pass the required country code from the agent's logic state to the tool call.
