"""Exercise HRMS source integrity during a real local image build."""

import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(
    os.environ.get("BENCH_BUILD_INTEGRATION") == "1",
    "set BENCH_BUILD_INTEGRATION=1 to run the networked image-build check",
)
class HRMSBuildPinTests(unittest.TestCase):
    """A build with a mismatched source commit must stop before installation."""

    def test_mismatched_hrms_commit_fails_the_build(self):
        """Reject a changed tag or incorrectly specified source commit."""
        docker_dir = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                "docker", "buildx", "build", "--progress=plain", "--output=type=cacheonly",
                "--build-arg", "HRMS_COMMIT=" + "0" * 40, str(docker_dir),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, "a mismatched HRMS commit was accepted")
        self.assertIn(
            "HRMS commit mismatch", result.stdout + result.stderr,
            "the build failed for a reason other than source integrity",
        )


if __name__ == "__main__":
    unittest.main()
