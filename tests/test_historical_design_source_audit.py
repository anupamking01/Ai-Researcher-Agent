"""Synthetic, outcome-free tests of the historical Git source attribution gate."""
import pytest

from scripts import audit_historical_design_source as audit


SOURCE = b'''VARIANTS = ("D3", "D6", "P6", "P6V")
async def main():
    tasks = []
    for task in tasks:
        for variant_id in VARIANTS:
            await run_agent(task=task, experiment_config=variant_id)
'''


def test_source_inspection_recognizes_task_then_variant_await():
    assert audit.inspect_runner_source(SOURCE) == ("D3", "D6", "P6", "P6V")


@pytest.mark.parametrize("source", [
    SOURCE.replace(b'"D3", "D6", "P6", "P6V"', b'"P6V", "D6", "P6", "D3"'),
    SOURCE.replace(b'for variant_id in VARIANTS:', b'for variant_id in reversed(VARIANTS):'),
    SOURCE.replace(b'for task in tasks:', b'for task in sorted(tasks):'),
    SOURCE.replace(b'await run_agent(', b'run_agent('),
    SOURCE + b'\nasync def main():\n    pass\n',
    SOURCE.replace(b'await run_agent(', b'await other_agent('),
    SOURCE.replace(b'async def main():', b'def main():'),
    SOURCE.replace(b'VARIANTS = (', b'VARIANTS = list((').replace(b'"P6V")', b'"P6V"))'),
    SOURCE.replace(b'for task in tasks:', b'for task in tasks:\n        await run_agent(task=task)'),
])
def test_source_inspection_rejects_unsupported_shapes(source):
    with pytest.raises(audit.HistoricalDesignSourceError):
        audit.inspect_runner_source(source)


def test_source_inspection_rejects_invalid_encoding_and_python():
    for source in (b'\xff', b'VARIANTS = ('):
        with pytest.raises(audit.HistoricalDesignSourceError):
            audit.inspect_runner_source(source)


def _fake_git(source=SOURCE, *, shallow=False, blob=None, ancestor_ok=True):
    expected = audit.RUNNER_BLOB_SHA if blob is None else blob
    def run(root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return (str(root) + "\n").encode()
        if args == ("rev-parse", "--is-shallow-repository"):
            return b"true\n" if shallow else b"false\n"
        if args == ("rev-parse", f"{audit.HISTORICAL_RUNNER_COMMIT}^{{commit}}"):
            return (audit.HISTORICAL_RUNNER_COMMIT + "\n").encode()
        if args[:2] == ("merge-base", "--is-ancestor"):
            if not ancestor_ok:
                raise audit.HistoricalDesignSourceError("historical runner is not an ancestor")
            return b""
        if args == ("rev-parse", f"{audit.HISTORICAL_RUNNER_COMMIT}:{audit.RUNNER_PATH}"):
            return (expected + "\n").encode()
        if args == ("show", f"{audit.HISTORICAL_RUNNER_COMMIT}:{audit.RUNNER_PATH}"):
            return source
        raise AssertionError(args)
    return run


def test_synthetic_checkout_receipt_has_explicit_claim_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "_git", _fake_git())
    result = audit.audit_checkout(tmp_path)
    assert result["historical_runner_task_then_variant_ast_checked"] is True
    assert result["source_linked_variant_order"] == ["D3", "D6", "P6", "P6V"]
    assert result["design_rank_task_treatment_position"] == 13
    assert result["original_treatment_execution_authenticated"] is False
    assert result["causal_effects_identified"] is False
    assert result["human_ratings_collected"] is False


@pytest.mark.parametrize("change", [
    {"shallow": True},
    {"blob": "a" * 40},
    {"ancestor_ok": False},
    {"source": SOURCE.replace(b'"D3", "D6", "P6", "P6V"', b'"P6V", "D6", "P6", "D3"')},
])
def test_synthetic_checkout_fails_closed_on_bad_history(tmp_path, monkeypatch, change):
    monkeypatch.setattr(audit, "_git", _fake_git(**change))
    with pytest.raises(audit.HistoricalDesignSourceError):
        audit.audit_checkout(tmp_path)


def test_git_unavailable_is_not_historical_evidence(tmp_path):
    with pytest.raises(audit.HistoricalDesignSourceError):
        audit._git(tmp_path, "show", "HEAD:missing-file")
