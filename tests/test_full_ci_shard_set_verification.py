"""Synthetic-only whole-run CI evidence replay; no research treatment reruns."""
import json
import shutil

import pytest

from scripts import select_full_ci_shard as selector
from scripts import verify_ci_test_evidence as producer
from scripts import verify_retained_ci_test_evidence as replay
from scripts import verify_full_ci_shard_set as whole

SHA = "a" * 40
DEPENDENCIES = {
    "requirements.txt": b"synthetic-app-pins",
    "requirements-ci.lock": b"synthetic-ci-pins",
}
CONTEXT = {
    "GITHUB_REPOSITORY": "anupamking01/Ai-Researcher-Agent",
    "GITHUB_SHA": SHA,
    "GITHUB_RUN_ID": "54321",
    "GITHUB_RUN_ATTEMPT": "2",
    "GITHUB_EVENT_NAME": "push",
}
KWARGS = {
    "checkout_sha": SHA, "run_id": "54321",
    "run_attempt": "2", "event": "push",
    "dependency_bytes": DEPENDENCIES,
}


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    tests = tmp_path / "tests"
    tests.mkdir()
    for index in range(32):
        (tests / f"test_{index:02d}.py").write_text(
            "def test_synthetic_only(): assert True\n", encoding="utf-8"
        )
    monkeypatch.setattr(producer, "ROOT", tmp_path)
    root = tmp_path / "downloaded"
    root.mkdir()
    discovered = selector.discover_modules(tmp_path)
    for shard in range(selector.SHARDS):
        selected = selector.select_shard(discovered, shard=shard)
        folder = root / f"shard-{shard}"
        folder.mkdir()
        inventory = "".join(f"{name}\n" for name in selected).encode()
        header = (
            f"VERA full-suite shard {shard}/16; selected {len(selected)} "
            f"modules; checkout {SHA}"
        )
        log = (
            header + "\n" + "\n".join(selected) + "\n"
            + producer.FIREWALL_MARKER + "\n"
            + "collecting ... collected 2 items\n"
            + "".join(
                f"{name}::test_synthetic_only PASSED [{(index + 1) * 50}%]\n"
                for index, name in enumerate(selected)
            )
            + "2 passed in 0.04s\n"
        ).encode()
        receipt = producer.build_receipt(
            log, context=CONTEXT, checkout_sha=SHA,
            dependency_bytes=DEPENDENCIES, selected_modules=inventory,
            shard=shard,
        )
        receipt["python_version"] = replay.runtime.PINNED_VERSION_TEXT
        (folder / "vera-offline-tests.log").write_bytes(log)
        (folder / "vera-offline-test-modules.txt").write_bytes(inventory)
        (folder / "vera-offline-test-receipt.json").write_bytes(
            (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
        )
    return root



@pytest.mark.parametrize("expected_size", [8, 3])
def test_untrusted_directory_inventory_stops_after_first_surplus_entry(
    tmp_path, monkeypatch, expected_size,
):
    """Synthetic overflow scan must never enumerate the rest of a huge input."""
    observed = []

    class FakeEntry:
        def __init__(self, name):
            self.name = name

    class FakeScandir:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            for index in range(1000):
                observed.append(index)
                if len(observed) > expected_size + 1:
                    raise AssertionError("unbounded evidence directory enumeration")
                yield FakeEntry(f"unexpected-{index}")

    monkeypatch.setattr(whole.os, "scandir", lambda _path: FakeScandir())
    with pytest.raises(ValueError, match="synthetic directory inventory mismatch"):
        whole._require_exact_entries(
            tmp_path, {f"expected-{index}" for index in range(expected_size)},
            message="synthetic directory inventory mismatch",
        )
    assert len(observed) == expected_size + 1


def test_indirect_parent_symlink_to_same_evidence_is_rejected(evidence):
    """Alias ancestors must fail, even if the receipts are unchanged."""
    alias = evidence.parent / "parent-alias"
    alias.symlink_to(evidence.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="aliased"):
        whole.verify_shard_set(alias / evidence.name, **KWARGS)


def test_parent_traversal_to_same_evidence_is_rejected(evidence):
    intermediate = evidence.parent / "intermediate"
    intermediate.mkdir()
    with pytest.raises(ValueError, match="parent components"):
        whole.verify_shard_set(intermediate / ".." / evidence.name, **KWARGS)


def test_redirecting_evidence_parent_to_same_bytes_mid_replay_is_rejected(
    evidence, monkeypatch,
):
    """An observed pathname swap after capture must veto the final PASS."""
    moved = evidence.parent / "saved-evidence"
    original_reader = producer.read_bounded_evidence
    changed = False

    def swap_after_first_read(path, *, maximum, label):
        nonlocal changed
        data = original_reader(path, maximum=maximum, label=label)
        if not changed and label == "shard 0 log":
            changed = True
            evidence.rename(moved)
            evidence.symlink_to(moved, target_is_directory=True)
        return data

    monkeypatch.setattr(whole.producer, "read_bounded_evidence", swap_after_first_read)
    with pytest.raises(ValueError, match="aliased|changed during replay"):
        whole.verify_shard_set(evidence, **KWARGS)
    assert changed


def test_pinned_evidence_directory_preserves_unrelated_failure(evidence):
    """An ordinary consumer failure retains its diagnostic when paths are stable."""
    with pytest.raises(ValueError, match="^synthetic receipt parse failure$"):
        with whole._pinned_directory_chain(evidence):
            raise ValueError("synthetic receipt parse failure")


def test_pinned_evidence_directory_detects_swap_during_failed_replay(evidence):
    """Check pinned ancestry on exception unwind, not only after a PASS."""
    moved = evidence.parent / "saved-evidence-on-error"
    with pytest.raises(ValueError, match="changed during replay"):
        with whole._pinned_directory_chain(evidence):
            evidence.rename(moved)
            evidence.symlink_to(moved, target_is_directory=True)
            raise ValueError("synthetic receipt parse failure")


def test_pinned_evidence_directory_detects_removal_during_failed_replay(evidence):
    """A vanished ancestor must not be mislabeled as a receipt parse failure."""
    moved = evidence.parent / "saved-evidence-removed"
    with pytest.raises(ValueError, match="missing, aliased, or changed"):
        with whole._pinned_directory_chain(evidence):
            evidence.rename(moved)
            raise ValueError("synthetic receipt parse failure")


def test_all_shards_replay_as_one_exact_run(evidence):
    result = whole.verify_shard_set(evidence, **KWARGS)
    assert result["shards_verified"] == 16
    assert result["source_test_modules_covered"] == 32
    assert result["aggregate_test_counts"] == {"passed": 32}
    assert [row["n_modules"] for row in result["per_shard"]] == [2] * 16
    assert result["experimental_treatments_or_evaluators_run"] is False
    assert result["human_validation_performed"] is False
    assert result["status"].endswith("not_independently_attested")



def test_full_sixteen_shard_replay_accepts_crlf_logs_without_rewriting_bytes(
    evidence,
):
    """All retained receipts bind original CRLF bytes and unchanged LF module lists."""
    for shard in range(selector.SHARDS):
        folder = evidence / f"shard-{shard}"
        log_path = folder / "vera-offline-tests.log"
        manifest = (folder / "vera-offline-test-modules.txt").read_bytes()
        crlf_log = log_path.read_bytes().replace(b"\n", b"\r\n")
        receipt = producer.build_receipt(
            crlf_log, context=CONTEXT, checkout_sha=SHA,
            dependency_bytes=DEPENDENCIES, selected_modules=manifest, shard=shard,
        )
        receipt["python_version"] = replay.runtime.PINNED_VERSION_TEXT
        log_path.write_bytes(crlf_log)
        (folder / "vera-offline-test-receipt.json").write_bytes(
            (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
        )

    result = whole.verify_shard_set(evidence, **KWARGS)
    assert result["shards_verified"] == selector.SHARDS
    assert result["source_test_modules_covered"] == 32
    assert result["aggregate_test_counts"] == {"passed": 32}


@pytest.mark.parametrize("case", [
    "missing_shard", "extra_shard", "duplicated_shard",
    "mixed_run", "mixed_attempt", "wrong_source",
    "tampered_log", "tampered_manifest", "tampered_receipt",
    "extra_file", "symlink_directory",
])
def test_incomplete_mixed_or_modified_shard_set_fails_closed(evidence, case):
    folder = evidence / "shard-4"
    if case == "missing_shard":
        shutil.rmtree(folder)
    elif case == "extra_shard":
        (evidence / "shard-16").mkdir()
    elif case == "duplicated_shard":
        shutil.rmtree(folder)
        shutil.copytree(evidence / "shard-3", folder)
    elif case in {"mixed_run", "mixed_attempt", "wrong_source"}:
        name = "vera-offline-test-receipt.json"
        receipt = json.loads((folder / name).read_text(encoding="utf-8"))
        key = {
            "mixed_run": "workflow_run_id",
            "mixed_attempt": "workflow_run_attempt",
            "wrong_source": "checkout_sha",
        }[case]
        receipt[key] = "unrelated" if case == "wrong_source" else "99999"
        (folder / name).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    elif case == "tampered_log":
        path = folder / "vera-offline-tests.log"
        path.write_bytes(path.read_bytes().replace(b"2 passed", b"3 passed"))
    elif case == "tampered_manifest":
        path = folder / "vera-offline-test-modules.txt"
        path.write_bytes(b"tests/test_00.py\n")
    elif case == "tampered_receipt":
        path = folder / "vera-offline-test-receipt.json"
        path.write_bytes(path.read_bytes().replace(b"sha256", b"SHa256", 1))
    elif case == "extra_file":
        (folder / "surprise.txt").write_text("not expected", encoding="utf-8")
    elif case == "symlink_directory":
        shutil.rmtree(folder)
        folder.symlink_to(evidence / "shard-3", target_is_directory=True)
    with pytest.raises(ValueError):
        whole.verify_shard_set(evidence, **KWARGS)


def test_mismatched_externally_supplied_run_identity_fails(evidence):
    with pytest.raises(ValueError):
        whole.verify_shard_set(
            evidence, **{**KWARGS, "run_id": "11111"}
        )


def test_direct_symlinked_retained_file_is_rejected(evidence):
    folder = evidence / "shard-2"
    path = folder / "vera-offline-tests.log"
    target = folder / "original-log"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ValueError, match="incomplete or unexpected"):
        whole.verify_shard_set(evidence, **KWARGS)


def test_complete_early_diagnostic_replay_rejects_altered_missing_and_mixed_receipts(
    tmp_path, monkeypatch,
):
    """Synthetic early logs: enforce all sixteen original-run receipt identities."""
    import hashlib
    from scripts import verify_ci_early_gate_evidence as early

    root = tmp_path / "early"
    root.mkdir()

    def fake_receipt(log, **kwargs):
        return {
            "passed_tests": 7,
            "log_sha256": hashlib.sha256(log).hexdigest(),
            "checkout_sha": kwargs["sha"],
            "workflow_run_id": kwargs["run_id"],
            "workflow_run_attempt": kwargs["attempt"],
            "workflow_event": kwargs["event"],
        }

    monkeypatch.setattr(early, "build_receipt", fake_receipt)
    for i in range(selector.SHARDS):
        folder = root / f"shard-{i}"
        folder.mkdir()
        log = f"synthetic-only shard {i}\\n".encode()
        (folder / "vera-stdlib-evaluation.log").write_bytes(log)
        (folder / "vera-stdlib-evaluation-receipt.json").write_bytes(
            early._canonical(fake_receipt(
                log, sha=SHA, run_id="54321", attempt="2", event="push",
            ))
        )

    kwargs = {
        "checkout_sha": SHA, "run_id": "54321",
        "run_attempt": "2", "event": "push",
    }
    verified = whole.verify_early_diagnostic_set(root, **kwargs)
    assert verified["shards_verified"] == selector.SHARDS
    assert verified["runner_or_original_research_source_attested"] is False

    receipt = root / "shard-5/vera-stdlib-evaluation-receipt.json"
    original = receipt.read_bytes()
    receipt.write_bytes(original.replace(b"54321", b"54322"))
    with pytest.raises(ValueError, match="disagrees"):
        whole.verify_early_diagnostic_set(root, **kwargs)
    receipt.write_bytes(original)

    log = root / "shard-5/vera-stdlib-evaluation.log"
    log.write_bytes(b"edited synthetic transcript\\n")
    with pytest.raises(ValueError, match="disagrees"):
        whole.verify_early_diagnostic_set(root, **kwargs)
    log.write_bytes(b"synthetic-only shard 5\\n")

    missing = root / "shard-5/vera-stdlib-evaluation-receipt.json"
    missing.unlink()
    with pytest.raises(ValueError, match="missing or unexpected"):
        whole.verify_early_diagnostic_set(root, **kwargs)


def test_early_diagnostic_replay_rejects_symlinked_evidence_root(tmp_path):
    actual = tmp_path / "real"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="missing, aliased, or changed"):
        whole.verify_early_diagnostic_set(
            alias, checkout_sha=SHA, run_id="54321",
            run_attempt="2", event="push",
        )

@pytest.mark.parametrize("mutation", [
    "none", "aggregate_count", "attempt", "early_hash", "duplicate_key",
    "format_only", "truncated", "oversized", "symlink",
])
def test_retained_aggregate_must_match_independently_replayed_bytes(
    evidence, monkeypatch, mutation,
):
    # Use the real 16-shard pytest replay, with a synthetic early-gate summary.
    early_result = {"shards_verified": 16, "per_shard": [
        {"shard": i, "log_sha256": "b" * 64} for i in range(16)
    ]}
    monkeypatch.setattr(whole, "verify_early_diagnostic_set",
                        lambda *args, **kwargs: early_result)
    result = whole.verify_shard_set(
        evidence, early_evidence_root=evidence.parent / "early", **KWARGS,
    )
    # Independent reproduction of the workflow's existing stdout contract.
    original = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    assert whole.canonical_aggregate_receipt(result) == original
    path = evidence.parent / "vera-full-shard-replay.json"
    if mutation == "aggregate_count":
        original = original.replace(b'"passed": 32', b'"passed": 33')
    elif mutation == "attempt":
        original = original.replace(b'"workflow_run_attempt": "2"',
                                    b'"workflow_run_attempt": "3"')
    elif mutation == "early_hash":
        original = original.replace(b"b" * 64, b"c" * 64, 1)
    elif mutation == "duplicate_key":
        original = original.replace(b'{\n', b'{\n  "shards_verified": 16,\n', 1)
    elif mutation == "format_only":
        original = json.dumps(result).encode()
    elif mutation == "truncated":
        original = original[:-10]
    elif mutation == "oversized":
        original = b"x" * (whole.MAX_AGGREGATE_RECEIPT_BYTES + 1)
    if mutation == "symlink":
        target = path.with_suffix(".original")
        target.write_bytes(original)
        path.symlink_to(target)
    else:
        path.write_bytes(original)
    if mutation == "none":
        whole.verify_retained_aggregate_receipt(result, path)
    else:
        with pytest.raises(ValueError):
            whole.verify_retained_aggregate_receipt(result, path)


def test_retained_aggregate_requires_early_diagnostic_replay(evidence):
    result = whole.verify_shard_set(evidence, **KWARGS)
    path = evidence.parent / "aggregate.json"
    path.write_bytes(whole.canonical_aggregate_receipt(result))
    with pytest.raises(ValueError, match="requires all early diagnostics"):
        whole.verify_retained_aggregate_receipt(result, path)


def test_aggregate_cli_requires_early_root_before_checkout(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "verify_full_ci_shard_set", "--evidence-root", "unused",
        "--checkout-sha", SHA, "--run-id", "54321", "--run-attempt", "2",
        "--event", "push", "--retained-aggregate-receipt", "unused.json",
    ])
    with pytest.raises(SystemExit) as exc:
        whole.main()
    assert exc.value.code == 2
    assert "requires --early-evidence-root" in capsys.readouterr().err
