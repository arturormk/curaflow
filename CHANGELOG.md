# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- CHANGELOG scaffold (provenance documented via ADR-0010 policy).
- Support for loading additional source/target plugins from a local `--plugins` directory.
- HTML helper `html_source_common.make_html_plugin` for custom BeautifulSoup-based scrapers with manifest-style fanout.
- `multiplex` meta-source plugin to expand parameterized source templates into per-instance sources (e.g. multi-language manifests) while keeping extraction names local.
 - QML helper `qml_target_common.make_qml_target_plugin` for YAML-backed `ListModel` targets that centralizes YAML IO and summaries while leaving QML construction in per-target `_render_qml` functions.

## [0.1.0] - 2025-09-13
### Added
- Initial GPT-generated scaffolding and instrumentation (ADRs, tests, CI, pre-commit, docs).
