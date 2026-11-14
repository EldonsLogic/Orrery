"""Check which files the engine's Docker build context exposes."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BuildContextTests(unittest.TestCase):
    """Exercise the engine's ignore rules through an actual BuildKit build."""

    def test_context_excludes_environment_file_but_includes_entrypoint(self):
        """Export a synthetic context and inspect the files BuildKit receives."""
        ignore_file = Path(__file__).resolve().parents[1] / ".dockerignore"
        with tempfile.TemporaryDirectory(prefix="bench-build-context-") as temporary:
            root = Path(temporary)
            context = root / "context"
            output = root / "output"
            context.mkdir()
            (context / "Dockerfile").write_text("FROM scratch\nCOPY . /\n")
            (context / "entrypoint.sh").write_text("#!/bin/sh\nexit 0\n")
            (context / ".env").write_text("SYNTHETIC_CONTEXT_MARKER=test-only\n")
            if ignore_file.is_file():
                shutil.copyfile(ignore_file, context / ".dockerignore")

            result = subprocess.run(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--progress=plain",
                    "--output",
                    f"type=local,dest={output}",
                    str(context),
                ],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "entrypoint.sh").is_file())
            self.assertFalse(
                (output / ".env").exists(),
                "the build context must exclude local environment files",
            )


if __name__ == "__main__":
    unittest.main()
