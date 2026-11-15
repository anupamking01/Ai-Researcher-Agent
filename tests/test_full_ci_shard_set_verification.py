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
    for index in range(16):
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
            f"VERA full-suite shard {shard}/8; selected {len(selected)} "
            f"modules; checkout {SHA}"
        )
        log = (
            header + "\n" + "\n".join(selected) + "\n"
            + producer.FIREWALL_MARKER + "\n"
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


def test_all_shards_replay_as_one_exact_run(evidence):
    result = whole.verify_shard_set(evidence, **KWARGS)
    assert result["shards_verified"] == 8
    assert result["source_test_modules_covered"] == 16
    assert result["aggregate_test_counts"] == {"passed": 16}
    assert [row["n_modules"] for row in result["per_shard"]] == [2] * 8
    assert result["experimental_treatments_or_evaluators_run"] is False
    assert result["human_validation_performed"] is False
    assert result["status"].endswith("not_independently_attested")


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
        (evidence / "shard-8").mkdir()
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
