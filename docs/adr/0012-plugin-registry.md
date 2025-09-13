# 0012: Introduce unified plugin registry

Status: Accepted

## Context

The MVP implemented plugin dispatch with ad-hoc `if/elif` chains in the CLI for a
small set of built-ins (`http_json`, `http_html`, `http_bytes`, `concat_json`).
This approach does not scale for: (a) third-party contributions, (b) incremental
addition of plugins without central modification, (c) resilience (one plugin
failing should not abort the entire fetch/build run), and (d) test isolation.

We also want the development log to illustrate a deliberate evolution towards
an extensible architecture while the codebase remains small.

## Decision

Introduce a lightweight in-process registry (`plugin_registry.py`) exposing:

- `@source_plugin(name)` / `@target_plugin(name)` decorators for auto-registration.
- `execute_source()` with exception capture returning a structured `FetchResult` TypedDict.
- Explicit `register_source/target` and `get_source/target` functions for programmatic use.
- Clear error types: `PluginRegistrationError`, `PluginNotFoundError`, `PluginExecutionError` (reserved for future richer reporting).
- Minimal, typed Protocols for source and target plugins.

`http_html` and `concat_json` migrated to decorators; legacy fetchers
`http_json` / `http_bytes` remain temporarily direct calls for simplicity but can
be migrated later (they already satisfy most semantics).

## Consequences

Positive:
- Extensible without central switch/case edits; third parties add one decorated function.
- Easier unit testing of registration, duplicate detection, and failure isolation.
- Clearer failure reporting path (structured error stored in result, not raised).
- Keeps surface area small and understandable while project is nascent.

Neutral / Trade-offs:
- Still requires explicit import of third-party module (no auto-discovery yet).
- Slight indirection introduced into CLI logic.

Future Work:
- Consider optional entry-point based discovery once packaging stabilizes.
- Add plugin metadata (version, description) and CLI list command.
- Provide structured logging / metrics hooks around executions.

## Alternatives Considered

1. Dynamic filesystem scanning for `plugins/*`: rejected (implicit magic, startup cost).
2. Python entry points now: deferred (premature for green-field stage; packaging churn likely).
3. Keeping ad-hoc branching: rejected (scales poorly, noisy diffs for each addition).

## Status Impact

Tests added (`test_plugin_registry.py`) covering registration, duplicates, decorator usage, and failure capture. README will be updated with authoring instructions.
