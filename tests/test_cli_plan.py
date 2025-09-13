import pathlib
import subprocess
import sys


def test_cli_plan_runs() -> None:
    manifest = pathlib.Path("example/manifest.yaml")
    assert manifest.exists()
    proc = subprocess.run(
        [sys.executable, "-m", "curaflow.cli", "plan", "-m", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    # Basic expected tokens
    assert "Sources" in proc.stdout
    assert "Targets" in proc.stdout
