# 0011 - Adopt third-party type stubs for critical libs

Status: Accepted
Date: 2025-09-13

## Context
The project enforces strict mypy checking. Expanding coverage to tests and scripts surfaced missing type information for external libraries (e.g. `yaml`). We faced a decision: either (a) ignore missing imports (globally or per-file) which would treat those modules as `Any`, or (b) install third-party stub packages such as `types-PyYAML` to retain type safety.

## Decision
We will install and maintain third-party stub packages (starting with `types-PyYAML`) for widely used runtime dependencies that lack bundled typing. This keeps strict type checking effective and avoids silent `Any` propagation.

## Consequences
- Stronger static guarantees; misuse of APIs will be caught earlier.
- Slight increase in dev dependency surface; occasional stub drift may require pinning or localized `# type: ignore` comments.
- Precedent: future libraries without types should first look for stubs before resorting to ignores.

## Alternatives Considered
1. Global `ignore_missing_imports = true`: Fast, but erodes type coverage and can mask real issues.
2. Per-file `# type: ignore[import]`: Reduces noise but still creates unchecked islands and encourages piecemeal exceptions.
3. Vendoring custom minimal stubs: Higher maintenance cost relative to installing community-maintained stub packages.

## Adoption & Maintenance
- Add stub packages to the project's dev dependency group.
- Review stub updates periodically during dependency refresh cycles.
- If a stub proves inaccurate, prefer precise inline ignores over disabling checks globally.
