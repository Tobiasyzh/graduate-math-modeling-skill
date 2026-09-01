"""Behavioral/integration checks for evidence utilities; standard library only."""
from pathlib import Path
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
from audit_project import audit
from common import load_json, safe_path, write_json

TEST_ROOT = SKILL.parent / "grad-math-modeling-workspace" / "tool-tests"
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class EvidenceToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=TEST_ROOT)
        self.base = Path(self.temp.name).resolve()
        if not self.base.is_relative_to(TEST_ROOT.resolve()):
            raise RuntimeError("Temporary cleanup target escaped test root")
        self.addCleanup(self.temp.cleanup)
        self.root = self.base / "project"
        result = self.call("init_project.py", self.root)
        self.assertEqual(result.returncode, 0, result.stderr)

    def call(self, script, *args):
        env = dict(os.environ, PYTHONUTF8="1")
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", env=env,
                              timeout=20, check=False)

    def prepare(self, body=None):
        (self.root / "data/raw/input.json").write_text('{"n":3}', encoding="utf-8")
        code = body or (
            "from pathlib import Path\nimport json,os\n"
            "n=json.loads(Path('data/raw/input.json').read_text())['n']\n"
            "Path('results/metrics.json').write_text(json.dumps({'value':n*5,'seed':int(os.environ['MODELING_SEED'])}))\n"
            "print('executed',n*5)\n")
        (self.root / "src/calculate.py").write_text(code, encoding="utf-8")

    def run_fixture(self, run_id="real-01", output="results/metrics.json", extra=()):
        return self.call("run_experiment.py", "--project", self.root, "--id", run_id,
                         "--seed", 42, "--input", "data/raw/input.json", "--source", "src/calculate.py",
                         "--output", output, "--metrics", output, *extra,
                         "--", sys.executable, "src/calculate.py")

    def declare(self, value=15, run_id="real-01"):
        project = load_json(self.root / "project.json")
        project["questions"] = [{"id":"Q1", "requirement":"Compute 3×5", "status":"verified",
                                 "run_ids":[run_id], "artifacts":["results/metrics.json"], "depends_on":[]}]
        write_json(self.root / "project.json", project)
        write_json(self.root / "claims.json", [{"id":"C1", "question_id":"Q1", "kind":"numeric",
                   "text":"Product is 15", "scope":"integer teaching instance", "run_id":run_id,
                   "metric":"value", "value":value, "unit":"dimensionless"}])

    def codes(self, stage="draft"):
        return {item["code"] for item in audit(self.root, stage)["issues"]}

    def test_initializer_preserves_existing_work(self):
        marker = self.root / "src/precious.txt"
        marker.write_text("keep", encoding="utf-8")
        self.assertNotEqual(self.call("init_project.py", self.root).returncode, 0)
        self.assertEqual(marker.read_text(), "keep")

    def test_actual_run_and_bound_claim_pass_draft(self):
        self.prepare()
        run = self.run_fixture(output="results\\metrics.json")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        evidence = load_json(self.root / "runs/real-01/run.json")
        self.assertEqual(evidence["metrics"], {"value":15, "seed":42})
        self.assertIn("executed 15", (self.root / "runs/real-01/stdout.log").read_text())
        self.assertEqual(evidence["metrics_path"], "results/metrics.json")
        self.declare()
        self.assertEqual(audit(self.root)["status"], "pass")

    def test_changed_input_source_and_output_are_detected(self):
        self.prepare()
        self.assertEqual(self.run_fixture().returncode, 0)
        self.declare()
        for relative in ["data/raw/input.json", "src/calculate.py", "results/metrics.json"]:
            with self.subTest(path=relative):
                path = self.root / relative
                old = path.read_bytes()
                path.write_bytes(old + b"\n ")
                self.assertIn("stale_evidence", self.codes())
                path.write_bytes(old)
        self.assertEqual(audit(self.root)["status"], "pass")

    def test_incorrect_numeric_claim_is_rejected(self):
        self.prepare()
        self.assertEqual(self.run_fixture().returncode, 0)
        self.declare(value=99)
        self.assertIn("claim_value", self.codes())

    def test_failed_command_cannot_support_claim_even_if_output_exists(self):
        self.prepare("from pathlib import Path\nPath('results/metrics.json').write_text('{\"value\":15}')\nraise SystemExit(7)\n")
        self.assertEqual(self.run_fixture().returncode, 1)
        self.declare()
        self.assertIn("failed_run", self.codes())

    def test_success_exit_without_output_is_still_failure(self):
        self.prepare("print('no output produced')\n")
        self.assertEqual(self.run_fixture().returncode, 1)
        evidence = load_json(self.root / "runs/real-01/run.json")
        self.assertEqual(evidence["status"], "failed")
        self.assertTrue(evidence["issues"])

    def test_preexisting_output_and_run_id_are_not_reused(self):
        self.prepare()
        self.assertEqual(self.run_fixture().returncode, 0)
        original = (self.root / "results/metrics.json").read_bytes()
        self.assertNotEqual(self.run_fixture().returncode, 0)
        self.assertNotEqual(self.run_fixture(run_id="real-02").returncode, 0)
        self.assertEqual((self.root / "results/metrics.json").read_bytes(), original)
        self.assertFalse((self.root / "runs/real-02").exists())

    def test_nonfinite_metrics_cannot_be_completed(self):
        for number in ["NaN", "Infinity", "1e999"]:
            with self.subTest(number=number):
                path = self.root / "checks/nonfinite.json"
                path.write_text('{"v":' + number + '}', encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_json(path)
        self.prepare("from pathlib import Path\nPath('results/metrics.json').write_text('{\"value\":NaN}')\n")
        self.assertEqual(self.run_fixture().returncode, 1)

    def test_paths_cannot_escape_project(self):
        for name in ["../outside.txt", "..\\outside.txt", "C:\\outside.txt", "/tmp/x", "\\\\server\\x", "", "."]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    safe_path(self.root, name)
        self.prepare()
        self.assertNotEqual(self.run_fixture(run_id="../bad").returncode, 0)

    def test_submission_requires_real_review_files_and_valid_ai_log(self):
        self.prepare()
        self.assertEqual(self.run_fixture().returncode, 0)
        self.declare()
        initial = self.codes("submission")
        self.assertIn("manual_review", initial)
        self.assertIn("ai_log", initial)
        project = load_json(self.root / "project.json")
        project["reviews"]["visual_inspection"] = {"status":"passed", "evidence":["checks/nonexistent.md"], "notes":"claimed review"}
        write_json(self.root / "project.json", project)
        (self.root / "ai_usage.jsonl").write_text("not json\n", encoding="utf-8")
        self.assertIn("missing_artifact", self.codes("submission"))
        self.assertIn("ai_log_format", self.codes("submission"))

    def test_submission_does_not_accept_unknown_live_rules_or_citations(self):
        self.prepare()
        self.assertEqual(self.run_fixture().returncode, 0)
        self.declare()
        project = load_json(self.root / "project.json")
        project["mode"] = "competition"
        write_json(self.root / "project.json", project)
        write_json(self.root / "sources.json", [{"id":"S1", "cited":True, "verification":"unverified"}])
        self.assertTrue({"rules_unverified", "ai_scope", "template_unverified", "unverified_citation"} <= self.codes("submission"))

    def test_freeze_detects_modified_exact_bytes(self):
        file = self.root / "paper/result.txt"
        file.write_text("version 1", encoding="utf-8")
        self.assertEqual(self.call("freeze_submission.py", self.root, "--file", "paper/result.txt").returncode, 0)
        self.assertEqual(self.call("freeze_submission.py", self.root, "--verify", "checks/submission_manifest.json").returncode, 0)
        file.write_text("version 2", encoding="utf-8")
        self.assertEqual(self.call("freeze_submission.py", self.root, "--verify", "checks/submission_manifest.json").returncode, 1)
        self.assertNotEqual(self.call("freeze_submission.py", self.root, "--file", "paper/result.txt").returncode, 0)

    def test_invalid_json_write_preserves_existing_file_and_cleans_temp(self):
        path = self.root / "checks/atomic.json"
        write_json(path, {"v":1})
        with self.assertRaises(ValueError):
            write_json(path, {"v":float("nan")})
        self.assertEqual(load_json(path), {"v":1})
        self.assertEqual(list(path.parent.glob("atomic.json.*.tmp")), [])
        write_json(path, {"v":2})
        self.assertEqual(load_json(path), {"v":2})

    def test_malformed_nested_records_report_instead_of_crash(self):
        project = load_json(self.root / "project.json")
        project["questions"] = [{"id":["bad"]}, {"id":"Q2", "status":"verified", "run_ids":[{}]}]
        project["reviews"] = []
        project["competition"] = []
        write_json(self.root / "project.json", project)
        report = audit(self.root, "submission")
        self.assertGreater(report["errors"], 0)


if __name__ == "__main__":
    capture = io.StringIO()
    start = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EvidenceToolsTests)
    result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
    elapsed = time.perf_counter() - start
    report = {"tests_run":result.testsRun, "failures":len(result.failures), "errors":len(result.errors),
              "duration_seconds":elapsed, "python":sys.version, "scope":"local deterministic integration tests; not award outcomes"}
    (TEST_ROOT / "tool-test-results.txt").write_text(capture.getvalue(), encoding="utf-8")
    write_json(TEST_ROOT / "tool-test-results.json", report)
    print(capture.getvalue())
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
