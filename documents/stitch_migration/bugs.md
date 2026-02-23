# Bug Tracker — Stitch Migration

Active bugs discovered during the migration. Each entry includes reproduction steps, root cause analysis, and the recommended fix.

---

## BUG-001: Top App Bar Overlays Main Content

**Status**: Open
**Severity**: High (visual regression — content inaccessible)
**File**: `frontend/src/app/layout.tsx`

### Symptom
The global top app bar (containing the CVviewer logo, search widget, and profile icon) visually overlaps the first row of content in the main pane. Job cards at the top of the Discovery Deck are partially hidden behind the header's background. Specifically, the company logo placeholders, top borders, and upper portions of job titles are obscured.
---
