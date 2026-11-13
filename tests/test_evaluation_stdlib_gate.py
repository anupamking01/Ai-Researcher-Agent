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

    def test_invalid_sampling_temperature_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "temperature"):
            RunTrace(run_id="bad", completed=True, source_count=0,
                     temperature=float("nan"))


if __name__ == "__main__":
    unittest.main()
