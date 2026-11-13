"""Dependency-free, source-checked diagnostic evaluation invariants for early CI.

Synthetic tests run under the pinned interpreter before pip installation.
They never establish full pytest success, experimental replication, or human
validation.
"""
from dataclasses import replace
from itertools import repeat
import unittest

from logic.evaluation import (
    RunTrace,
    MAX_DIAGNOSTIC_REFERENCE_TASKS,
    aggregate_runs_by_task,
    paired_bootstrap_confidence_interval_by_task,
    paired_run_trace_bootstrap_by_task,
)

TASKS = ("task-a", "task-b")
QUESTIONS = {"task-a": "Frozen question A?", "task-b": "Frozen question B?"}
TASK_SET = "synthetic-early-gate"


def make_trace(variant, task, *, supported=0, completed=True):
    return RunTrace(
        run_id=f"{variant}-{task}",
        completed=completed,
        source_count=1 if completed else 0,
        supported_claim_count=supported if completed else 0,
        unsupported_claim_count=1 - supported if completed else 0,
        variant_id=variant,
        task_set_id=TASK_SET,
        task_id=task,
        question=QUESTIONS[task],
    )


def compare(baseline, candidate, **extra):
    return paired_run_trace_bootstrap_by_task(
        baseline, candidate,
        baseline_variant_id="D3",
        candidate_variant_id="D6",
        task_set_id=TASK_SET,
        expected_task_ids=TASKS,
        expected_questions_by_task=QUESTIONS,
        n_resamples=12,
        seed=19,
        **extra,
    )


class DependencyFreeEvaluationGate(unittest.TestCase):
    def test_complete_pairing_is_seeded_and_order_invariant(self):
        baseline = [make_trace("D3", "task-a"), make_trace("D3", "task-b", supported=1)]
        candidate = [make_trace("D6", "task-a", supported=1),
                     make_trace("D6", "task-b", supported=1)]
        forward = compare(iter(baseline), iter(candidate))
        reversed_order = compare(iter(reversed(baseline)), iter(reversed(candidate)))
        self.assertEqual(forward, reversed_order)
        self.assertEqual(forward["task_ids"], sorted(TASKS))
        self.assertEqual(forward["n_pairs"], 2)
        self.assertEqual(forward["mean_delta"], 0.5)

    def test_swapped_question_rejected_before_candidate_is_read(self):
        baseline = [replace(make_trace("D3", "task-a"), question=QUESTIONS["task-b"]),
                    make_trace("D3", "task-b")]

        def forbidden_candidate():
            raise AssertionError("bad baseline must not read candidate")
            yield make_trace("D6", "task-a")

        with self.assertRaisesRegex(ValueError, "task question mismatch"):
            compare(iter(baseline), forbidden_candidate())

    def test_unending_trace_stream_is_bounded_by_task_manifest(self):
        with self.assertRaisesRegex(ValueError, "more records"):
            compare(repeat(make_trace("D3", "task-a")), iter(()))

    def test_failed_zero_source_task_remains_in_denominator(self):
        records = [make_trace("D3", "task-a", completed=False),
                   make_trace("D3", "task-b", supported=1)]
        summary = aggregate_runs_by_task(
            iter(records), variant_id="D3", task_set_id=TASK_SET,
            expected_task_ids=TASKS, expected_questions_by_task=QUESTIONS,
        )
        self.assertEqual(summary["n_runs"], 2)
        self.assertEqual(summary["completion_rate"], 0.5)
        self.assertEqual(summary["avg_claim_support_rate"], 0.5)

    def test_numeric_bootstrap_keeps_paired_differences_seeded(self):
        kwargs = {"expected_task_ids": TASKS, "n_resamples": 12, "seed": 7}
        first = paired_bootstrap_confidence_interval_by_task(
            iter([("task-a", 0.0), ("task-b", 1.0)]),
            iter([("task-b", 1.0), ("task-a", 1.0)]), **kwargs,
        )
        second = paired_bootstrap_confidence_interval_by_task(
            iter([("task-b", 1.0), ("task-a", 0.0)]),
            iter([("task-a", 1.0), ("task-b", 1.0)]), **kwargs,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["mean_delta"], 0.5)

    def test_infinite_independent_manifest_fails_before_observation_reads(self):
        reads = {"reference": 0, "baseline": 0, "candidate": 0}

        def reference():
            index = 0
            while True:
                reads["reference"] += 1
                yield f"task-{index}"
                index += 1

        def arm(name):
            reads[name] += 1
            raise AssertionError("invalid reference read an observation")
            yield (TASKS[0], 0.0)

        with self.assertRaisesRegex(ValueError, "diagnostic reference limit"):
            paired_bootstrap_confidence_interval_by_task(
                arm("baseline"), arm("candidate"),
                expected_task_ids=reference(), n_resamples=4,
            )
        self.assertEqual(reads, {
            "reference": MAX_DIAGNOSTIC_REFERENCE_TASKS + 1,
            "baseline": 0, "candidate": 0,
        })

    def test_invalid_sampling_temperature_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "temperature"):
            RunTrace(run_id="bad", completed=True, source_count=0,
                     temperature=float("nan"))


    def test_early_receipt_replays_exact_success_and_rejects_identity_tamper(self):
        from scripts.verify_ci_early_gate_evidence import build_receipt, SOURCES
        cases = [
            f"test_{n} (test_evaluation_stdlib_gate.DependencyFreeEvaluationGate.test_{n}) ... ok"
            for n in ("a", "b", "c", "d", "e", "f", "g")
        ]
        log = ("VERA EARLY DIAGNOSTIC: sha=" + "a" * 40
               + " run=42 attempt=1 event=push\n"
               + "\n".join(cases) + "\n"
               + "-" * 70 + "\nRan 7 tests in 0.001s\n\nOK\n").encode()
        kwargs = dict(sha="a" * 40, run_id="42", attempt="1",
                      event="push", repository="anupamking01/Ai-Researcher-Agent",
                      sources={name: name.encode() for name in SOURCES})
        receipt = build_receipt(log, **kwargs)
        self.assertEqual(receipt["passed_tests"], 7)
        self.assertFalse(receipt["full_pytest_success_established"])
        with self.assertRaisesRegex(ValueError, "identity header"):
            build_receipt(log, **{**kwargs, "sha": "b" * 40})
        with self.assertRaisesRegex(ValueError, "completion count"):
            build_receipt(log.replace(b"Ran 7 tests", b"Ran 8 tests"), **kwargs)
        with self.assertRaisesRegex(ValueError, "final successful unittest result"):
            build_receipt(log.replace(b"\nOK\n", b"\nOK\nPASS\n"), **kwargs)

    def test_early_receipt_rejects_missing_tests_and_failed_output(self):
        from scripts.verify_ci_early_gate_evidence import build_receipt, SOURCES
        kwargs = dict(sha="a" * 40, run_id="42", attempt="1",
                      event="push", repository="anupamking01/Ai-Researcher-Agent",
                      sources={name: b"pinned" for name in SOURCES})
        for log in (b"", b"Ran 7 tests in 0.001s\nOK\n",
                    b"VERA EARLY DIAGNOSTIC: sha=" + b"a" * 40 +
                    b" run=42 attempt=1 event=push\nRan 7 tests in 0.001s\nFAILED\n"):
            with self.assertRaises(ValueError):
                build_receipt(log, **kwargs)

if __name__ == "__main__":
    unittest.main()
