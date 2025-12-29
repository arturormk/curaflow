# 0002-hierarchical-fanout-design
Status: Accepted
Date: 2025-09-13

## Context
Many curated web datasets require multi-level traversal (index → entity pages → assets). Curaflow must support dynamic discovery of additional sources during a run, persisting them for incremental refreshes.

## Decision
Implement hierarchical fanout in source plugins (currently `http_html` and `http_xml`). A source fetch may return child source specs which are appended to the processing queue and persisted in `.curaflow/meta/sources_dynamic.json`. Children are treated as first-class sources for dependency and build planning.

Fanout is always expressed in terms of *local extraction keys* on the parent source, not other source names. In manifests this appears as:

- `extract[*].name` → produces an entry under `extractions[<name>]` in the parent YAML.
- `fanout[*].from` → refers to one of those extraction keys.

Dynamic child sources created via fanout (or higher-level meta-plugins such as `multiplex`) are identified by their own `name` values and behave like any other source: their normalized data is written to `data/sources/<name>.yaml` and any associated binary payloads to `data/raw/<name>.*`.

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
