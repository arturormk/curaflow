# 0010-ai-curation-policy
Status: Accepted
Date: 2025-09-13

## Context
Curaflow is developed with AI assistance under human curation. Transparency and controlled evolution are essential to maintain trust and reproducibility.

## Decision
Adopt an AI curation policy: AI produces drafts; human curator approves intent. Every meaningful behavior change must include (a) ADR update/addition if architectural/process, (b) tests, (c) passing pre-commit + CI. Attribution is explicit in README (Attribution & Curation section) and `AUTHORS`. Large AI-assisted batches may include a `Curated-By:` commit footer.

## Consequences
Positive:
- Clear provenance chain.
- Encourages disciplined, test-first evolution.

Negative / Trade-offs:
- Additional documentation overhead.

Follow-ups:
- Add AUTHORS + README attribution section.
- Implement pre-commit/CI checks for ADR index integrity.
