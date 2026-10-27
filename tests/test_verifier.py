"""Subprocess fixtures are temporary unit data, never formal evidence."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from safeflow.core.definition import Definition
from safeflow.verification import build_bundle, UppaalVerifier, VerificationGate
from test_core import EXAMPLE


class VerifierContractTests(unittest.TestCase):
    def setup_bundle(self, tmp):
        root = Path(tmp)
        exe = root/'test-verifier'; exe.write_bytes(b'unit-test-fixture-not-real-UPPAAL')
        d = Definition.load(EXAMPLE)
        bundle = build_bundle(d, root/'bundle')
        return d, bundle, UppaalVerifier(exe)

    def test_complete_results_are_bound_to_outputs_and_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, bundle, verifier = self.setup_bundle(tmp)
            def fake_run(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, 'test fixture version' if '--version' in args else '-- Formula is satisfied.\n', '')
            with patch('safeflow.verification.subprocess.run', side_effect=fake_run):
                report = verifier.verify(bundle)
            self.assertEqual(report['status'], 'passed')
            self.assertEqual(VerificationGate(bundle).require(d)['status'], 'passed')
            path = bundle/'verifier-000.txt'; path.write_text('-- Formula is NOT satisfied.\n')
            with self.assertRaises(ValueError): VerificationGate(bundle).require(d)

    def test_nonzero_license_error_and_timeout_never_pass(self):
        for response in ('license', 'timeout', 'missing_output', 'failed'):
            with tempfile.TemporaryDirectory() as tmp:
                d, bundle, verifier = self.setup_bundle(tmp)
                def fake_run(args, **kwargs):
                    if '--version' in args: return subprocess.CompletedProcess(args, 0, 'fixture', '')
                    if response == 'timeout': raise subprocess.TimeoutExpired(args, 1)
                    if response == 'license': return subprocess.CompletedProcess(args, 1, '', 'License does not cover verifier.')
                    return subprocess.CompletedProcess(args, 0, 'Formula is NOT satisfied.' if response == 'failed' else '', '')
                with patch('safeflow.verification.subprocess.run', side_effect=fake_run): report = verifier.verify(bundle)
                self.assertEqual(report['status'], 'not_ready')
                with self.assertRaises(ValueError): VerificationGate(bundle).require(d)

    def test_incomplete_results_and_changed_binary_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, bundle, verifier = self.setup_bundle(tmp)
            with patch('safeflow.verification.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'Formula is satisfied.', '')):
                report = verifier.verify(bundle)
            report['results'].pop()
            (bundle/'verification.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'incomplete'): VerificationGate(bundle).require(d)
            with patch('safeflow.verification.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'Formula is satisfied.', '')):
                verifier.verify(bundle)
            verifier.executable.write_bytes(b'changed-fixture')
            with self.assertRaisesRegex(ValueError, 'binary_changed'): VerificationGate(bundle).require(d)


@unittest.skipUnless(os.environ.get('SAFEFLOW_VERIFYTA'), 'Set SAFEFLOW_VERIFYTA to run real UPPAAL integration')
class RealUppaalTests(unittest.TestCase):
    def test_real_queries_and_mutated_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            definition = Definition.load(EXAMPLE)
            verifier = UppaalVerifier(os.environ['SAFEFLOW_VERIFYTA'])
            bundle = build_bundle(definition, Path(tmp)/'original')
            report = verifier.verify(bundle)
            if report['results'][0]['status'] in ('unavailable', 'timeout'):
                self.skipTest((bundle/'verifier-000.txt').read_text(encoding='utf-8').strip())
            self.assertEqual(report['status'], 'passed')
            VerificationGate(bundle).require(definition)
            data = definition.data
            data['transitions'][2]['outcome'] = 'allow'
            mutated = build_bundle(Definition(data), Path(tmp)/'mutated')
            result = verifier.verify(mutated)
            conflict = next(x for x in result['results'] if x['id'] == 'no_ai_conflict')
            self.assertEqual(conflict['status'], 'failed')
