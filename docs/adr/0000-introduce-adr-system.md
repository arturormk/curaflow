# 0000-introduce-adr-system
Status: Accepted
Date: 2025-09-13

## Context
Curaflow is an AI-assisted, human-curated project. We require a lightweight, explicit mechanism to record architectural and process decisions to enable safe evolution and transparent provenance.

## Decision
Adopt Architecture Decision Records (ADRs) stored in `docs/adr/`. Use 4-digit numeric prefixes, incremental. Each ADR includes Context, Decision, Consequences. Status keywords: Proposed, Accepted, Superseded. An index will be auto-generated in `docs/adr/README.md` via a script and enforced by pre-commit and CI.

## Consequences
Positive:
- Shared understanding of rationale behind changes.
- Enables automated linting of decision corpus.
- Facilitates AI assistants referencing past intent.

Negative / Trade-offs:
- Slight upfront writing overhead.

Follow-ups:
- Implement index + lint scripts.
- Reference ADR IDs in code/doc comments where relevant.
