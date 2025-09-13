# 0002-hierarchical-fanout-design
Status: Accepted
Date: 2025-09-13

## Context
Many curated web datasets require multi-level traversal (index → entity pages → assets). Curaflow must support dynamic discovery of additional sources during a run, persisting them for incremental refreshes.

## Decision
Implement hierarchical fanout in source plugins (currently `http_html`). A source fetch may return child source specs which are appended to the processing queue and persisted in `.curaflow/meta/sources_dynamic.json`. Children are treated as first-class sources for dependency and build planning.

## Consequences
Positive:
- Enables scalable breadth-first expansion without pre-declaring all pages.
- Incremental updates skip unchanged resources via conditional GET + content digest.

Negative / Trade-offs:
- More complex fetch orchestration logic.
- Potential uncontrolled growth if fanout rules are too permissive (needs guardrails later).

Follow-ups:
- Add guardrails for fanout depth / count (future ADR).
- Add tests to ensure dynamic sources integrate with build dependency graph.
