from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import curaflow.cli as cli


def test_lang_targets_manifest_expansion(tmp_path: Path) -> None:
    """lang_targets pseudo-plugin expands into concrete language-specific targets.

    This keeps the logic purely at manifest-load time so the rest of the
    DAG/build pipeline sees only normal TargetSpec entries.
    """

    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        dedent(
            """
            sources: []
            targets:
              - name: lang-qml
                plugin: lang_targets
                params:
                  languages: ["es", "en"]
                  targets:
                    - name: "$lang$_example_qml"
                      plugin: debug_print
                      deps: ["$lang$:example"]
                      params:
                        base_dir: "$lang$/example"
            """
        ).lstrip()
        + "\n",
        encoding="utf-8",
    )

    sources, targets = cli.load_manifest(manifest)

    assert sources == {}
    # Two concrete targets, one per language
    assert set(targets.keys()) == {"es_example_qml", "en_example_qml"}

    es = targets["es_example_qml"]
    en = targets["en_example_qml"]

    assert es.deps == ["es:example"]
    assert en.deps == ["en:example"]

    assert es.params.get("base_dir") == "es/example"
    assert en.params.get("base_dir") == "en/example"
