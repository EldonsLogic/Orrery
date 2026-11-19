"""Execute the real INF-003 workflow filter with controlled Git failures/diffs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
KEYS = {'blueprint', 'control_plane', 'datasets', 'discovery', 'gateway',
        'operate', 'studio', 'engine', 'evals', 'scripts', 'infra', 'components'}


def filter_script():
    """Extract the shell verbatim, without requiring a YAML package in CI."""
    workflow = (ROOT / '.github/workflows/tests.yml').read_text()
    block = workflow.split('        run: |\n', 1)[1].split('\n      # ---', 1)[0]
    return '\n'.join(line[10:] for line in block.splitlines())


class ServiceFilterTests(unittest.TestCase):
    """Assert suite selections rather than matching shell implementation text."""

    def select(self, changed, failure='', event='pull_request', expected_code=0):
        """Run the checked-in shell against a stub git executable."""
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'changes').write_text(changed)
            git = directory / 'git'
            git.write_text('#!/bin/bash\n'
                           'if [ "$1" = "$FAIL_COMMAND" ]; then exit 128; fi\n'
                           'if [ "$1" = merge-base ]; then echo base; '
                           'else cat "$CHANGES_FILE"; fi\n')
            git.chmod(0o755)
            output = directory / 'output'
            result = subprocess.run(['bash', '-c', filter_script()], text=True,
                capture_output=True, cwd=ROOT, env={**os.environ, 'PATH': f'{directory}:' + os.environ['PATH'],
                'FAIL_COMMAND': failure, 'CHANGES_FILE': str(directory / 'changes'),
                'EVENT_NAME': event, 'BASE_SHA': 'base', 'HEAD_SHA': 'head',
                'GITHUB_OUTPUT': str(output)})
            self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
            if expected_code:
                self.assertIn('Unmapped test', result.stdout)
                return {}
            return dict(line.split('=', 1) for line in output.read_text().splitlines())

    def test_git_failures_and_empty_diffs_select_every_suite(self):
        for failure in ('merge-base', 'diff', ''):
            with self.subTest(failure=failure):
                self.assertEqual(self.select('', failure), dict.fromkeys(KEYS, 'true'))

    def test_main_and_manual_runs_select_every_suite(self):
        for event in ('push', 'workflow_dispatch'):
            self.assertEqual(self.select('', event=event), dict.fromkeys(KEYS, 'true'))

    def test_shared_scripts_select_every_suite(self):
        self.assertEqual(self.select('scripts/check_contracts.py\n'), dict.fromkeys(KEYS, 'true'))

    def test_large_diff_preserves_dependency_selection(self):
        changed = ''.join(f'services/blueprint/file_{i}.py\n' for i in range(20000))
        selected = self.select(changed)
        for name in ('blueprint', 'gateway', 'engine', 'discovery', 'operate', 'studio', 'evals'):
            with self.subTest(name=name):
                self.assertEqual(selected[name], 'true')

    def test_unknown_service_selects_every_suite(self):
        self.assertEqual(self.select('services/new_service/handler.py\n'),
                         dict.fromkeys(KEYS, 'true'))

    def test_gateway_only_change_stays_scoped(self):
        selected = self.select('services/gateway/metering.py\n')
        self.assertEqual(selected['gateway'], 'true')
        self.assertEqual(selected['blueprint'], 'false')

    def test_unmapped_test_cannot_silently_skip(self):
        self.select('infra/new_suite/tests/test_new.py\n', expected_code=1)

    def test_shared_contracts_and_cross_service_dependencies(self):
        """A dependency edit must exercise each downstream consumer."""
        self.assertEqual(self.select('contracts/event.schema.json\n'),
                         dict.fromkeys(KEYS, 'true'))
        for path, consumers in (
            ('services/blueprint/events/evstream.py', ('gateway', 'operate', 'engine', 'discovery', 'studio', 'evals')),
            ('services/datasets/generator.py', ('studio',)),
            ('services/control-plane/identity.py', ('operate',)),
            ('components/core/trading_ar/pack.py', ('studio', 'engine')),
        ):
            selected = self.select(path + '\n')
            for consumer in consumers:
                with self.subTest(path=path, consumer=consumer):
                    self.assertEqual(selected[consumer], 'true')
