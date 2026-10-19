"""Core offline analysis for frozen human ratings.

The analysis snapshots every blinded artifact before pre-unblinding verification,
then snapshots treatment-mapping artifacts only after that blinded gate passes.
Verification and downstream analysis therefore consume the same captured bytes,
so an editor save cannot change the analyzed revision after it was verified.
"""
import hashlib
import json
import math
import os
import random
import stat
import statistics
import tempfile
from pathlib import Path

from scripts import build_human_eval_packet as packet
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as blind_verify
from scripts import verify_human_eval_packet as map_verify

ROOT = Path(__file__).resolve().parents[1]
PACKET_ROOT = ROOT / "outputs" / "human_eval"
FREEZE_ROOT = PACKET_ROOT / "frozen-v1"
PLAN = ROOT / "paper" / "HUMAN_EVAL_ANALYSIS_PLAN.md"
TASKS = packet.DEFAULT_TASK_MANIFEST
DIMS = freeze.SCORE_FIELDS
VARIANTS = packet.EXPECTED_VARIANTS
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
SEED = 20260925
BOOTSTRAP_DRAWS = 20_000
FROZEN_ANALYSIS_PLAN_SHA256 = (
    "df347ab0602169c469fb38e14201b66ac250b693e51c1dd8b5ef70a3a11e78c6"
)


def fingerprint(path, *, logical_path=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing regular file: {path}")
    data = path.read_bytes()
    return {
        "path": str(logical_path) if logical_path is not None else path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _snapshot_file(source, destination, *, label):
    """Capture one path-bound regular-file generation into scratch space."""
    source = Path(source)
    destination = Path(destination)

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_descriptor = os.open(source.parent, directory_flags)
    except OSError as exc:
        raise ValueError(
            f"{label} parent must be a regular directory: {source.parent}"
        ) from exc

    try:
        parent = os.fstat(parent_descriptor)
        if not stat.S_ISDIR(parent.st_mode):
            raise ValueError(
                f"{label} parent must be a regular directory: {source.parent}"
            )

        file_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        file_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(source.name, file_flags, dir_fd=parent_descriptor)
        except OSError as exc:
            raise ValueError(f"{label} must be a regular file: {source}") from exc

        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(f"{label} must be a regular file: {source}")

            chunks = []
            offset = 0
            while True:
                chunk = os.pread(descriptor, 1024 * 1024, offset)
                if not chunk:
                    break
                chunks.append(chunk)
                offset += len(chunk)
            after = os.fstat(descriptor)
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if before_identity != after_identity:
                raise ValueError(f"{label} changed while it was being read")

            try:
                current = os.stat(
                    source.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                current_parent = os.stat(source.parent, follow_symlinks=False)
            except OSError as exc:
                raise ValueError(
                    f"{label} changed while it was being snapshotted"
                ) from exc
            if (
                not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != after_identity[:2]
                or not stat.S_ISDIR(current_parent.st_mode)
                or (current_parent.st_dev, current_parent.st_ino)
                != (parent.st_dev, parent.st_ino)
            ):
                raise ValueError(f"{label} changed while it was being snapshotted")
            content = b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_descriptor)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def _snapshot_raw_ratings(rating_paths, root):
    snapshots = []
    for index, path in enumerate(rating_paths, start=1):
        path = Path(path)
        destination = Path(root) / f"{index:04d}" / path.name
        snapshots.append(_snapshot_file(path, destination, label=f"raw rating input {index}"))
    return snapshots


def _open_snapshot_directory(path, *, label):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular directory: {path}") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"{label} must be a regular directory: {path}")
    return descriptor


def _require_snapshot_directory_binding(path, descriptor, *, label):
    opened = os.fstat(descriptor)
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"{label} changed while it was being snapshotted") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(f"{label} changed while it was being snapshotted")


def _snapshot_entry_identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _snapshot_tree_file(directory_descriptor, name, destination, *, label, expected):
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular file") from exc

    try:
        before = os.fstat(descriptor)
        expected_identity = (expected.st_dev, expected.st_ino)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != expected_identity
        ):
            raise ValueError(f"{label} changed while it was being snapshotted")

        chunks = []
        offset = 0
        while True:
            chunk = os.pread(descriptor, 1024 * 1024, offset)
            if not chunk:
                break
            chunks.append(chunk)
            offset += len(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity:
            raise ValueError(f"{label} changed while it was being read")
        try:
            current = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                f"{label} changed while it was being snapshotted"
            ) from exc
        if (
            not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != after_identity[:2]
        ):
            raise ValueError(f"{label} changed while it was being snapshotted")
        content = b"".join(chunks)
    finally:
        os.close(descriptor)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def _snapshot_directory_descriptor(
    source_root,
    destination_root,
    descriptor,
    *,
    label,
    parent_descriptor=None,
    entry_name=None,
):
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        raise ValueError(f"{label} must be a regular directory: {source_root}")
    try:
        names_before = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise ValueError(f"{label} could not be enumerated: {source_root}") from exc

    metadata_by_name = {}
    for name in names_before:
        child_label = f"{label} {name}"
        try:
            metadata_by_name[name] = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                f"{child_label} changed while it was being snapshotted"
            ) from exc

    destination_root.mkdir(parents=True, exist_ok=False)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    for name in names_before:
        child_label = f"{label} {name}"
        destination = destination_root / name
        metadata = metadata_by_name[name]
        if stat.S_ISDIR(metadata.st_mode):
            try:
                child_descriptor = os.open(name, directory_flags, dir_fd=descriptor)
            except OSError as exc:
                raise ValueError(
                    f"{child_label} changed while it was being snapshotted"
                ) from exc
            try:
                child_opened = os.fstat(child_descriptor)
                if (child_opened.st_dev, child_opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise ValueError(
                        f"{child_label} changed while it was being snapshotted"
                    )
                _snapshot_directory_descriptor(
                    Path(source_root) / name,
                    destination,
                    child_descriptor,
                    label=child_label,
                    parent_descriptor=descriptor,
                    entry_name=name,
                )
            finally:
                os.close(child_descriptor)
        elif stat.S_ISREG(metadata.st_mode):
            _snapshot_tree_file(
                descriptor,
                name,
                destination,
                label=child_label,
                expected=metadata,
            )
        else:
            raise ValueError(
                f"{child_label} must be a regular file or directory: "
                f"{Path(source_root) / name}"
            )

    try:
        names_after = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise ValueError(
            f"{label} changed while it was being snapshotted"
        ) from exc
    if names_after != names_before:
        raise ValueError(f"{label} changed while it was being snapshotted")
    if _snapshot_entry_identity(os.fstat(descriptor)) != _snapshot_entry_identity(
        opened
    ):
        raise ValueError(f"{label} changed while it was being snapshotted")
    for name in names_before:
        try:
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise ValueError(
                f"{label} {name} changed while it was being snapshotted"
            ) from exc
        if _snapshot_entry_identity(current) != _snapshot_entry_identity(
            metadata_by_name[name]
        ):
            raise ValueError(
                f"{label} {name} changed while it was being snapshotted"
            )

    if parent_descriptor is None:
        _require_snapshot_directory_binding(source_root, descriptor, label=label)
    else:
        try:
            current = os.stat(
                entry_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                f"{label} changed while it was being snapshotted"
            ) from exc
        if (
            not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValueError(f"{label} changed while it was being snapshotted")


def _snapshot_directory_tree(source_root, destination_root, *, label):
    """Copy one descriptor-bound tree and reject concurrent path changes."""
    source_root = Path(source_root)
    destination_root = Path(destination_root)
    descriptor = _open_snapshot_directory(source_root, label=label)
    try:
        _snapshot_directory_descriptor(
            source_root,
            destination_root,
            descriptor,
            label=label,
        )
    finally:
        os.close(descriptor)


def _reject_undeclared_freeze_sidecars(
    freeze_root,
    *,
    observed_names=None,
    observed_metadata=None,
    root_descriptor=None,
):
    """Inspect source names without opening any undeclared freeze artifact."""
    freeze_root = Path(freeze_root)
    allowed_names = {
        *freeze.OUTPUT_FILES,
        "raw_rating_inputs",
        "provenance",
        "governing_inputs",
        "submission_preflights",
    }
    root_names = (
        {child.name for child in freeze_root.iterdir()}
        if observed_names is None
        else set(observed_names)
    )
    root_extra_names = root_names - allowed_names

    if root_descriptor is not None and "provenance" in root_names:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            current_provenance = os.stat(
                "provenance",
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                "freeze provenance changed while it was being inspected"
            ) from exc
        provenance_metadata = (
            observed_metadata.get("provenance")
            if observed_metadata is not None
            else current_provenance
        )
        if _snapshot_entry_identity(current_provenance) != _snapshot_entry_identity(
            provenance_metadata
        ):
            raise ValueError(
                "freeze provenance changed while it was being inspected"
            )
        if not stat.S_ISDIR(provenance_metadata.st_mode):
            if root_extra_names:
                raise ValueError(
                    "freeze root contents mismatch: undeclared artifacts "
                    f"{sorted(root_extra_names)!r}"
                )
            return
        try:
            provenance_descriptor = os.open(
                "provenance",
                directory_flags,
                dir_fd=root_descriptor,
            )
        except OSError as exc:
            raise ValueError(
                "freeze provenance changed while it was being inspected"
            ) from exc
        try:
            provenance_opened = os.fstat(provenance_descriptor)
            if _snapshot_entry_identity(
                provenance_opened
            ) != _snapshot_entry_identity(provenance_metadata):
                raise ValueError(
                    "freeze provenance changed while it was being inspected"
                )
            names_before = tuple(sorted(os.listdir(provenance_descriptor)))
            provenance_extra_names = set(names_before) - {
                "freeze_human_eval_ratings.py",
                "build_human_eval_packet.py",
            }
            if provenance_extra_names:
                raise ValueError(
                    "provenance archive contents mismatch: "
                    f"undeclared artifacts {sorted(provenance_extra_names)!r}"
                )
            for filename, label in (
                ("freeze_human_eval_ratings.py", "blinded freeze producer"),
                ("build_human_eval_packet.py", "blinded content validator"),
            ):
                if filename not in names_before:
                    continue
                try:
                    child = os.stat(
                        filename,
                        dir_fd=provenance_descriptor,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise ValueError(f"{label} must be a regular file") from exc
                if not stat.S_ISREG(child.st_mode):
                    raise ValueError(f"{label} must be a regular file")
            names_after = tuple(sorted(os.listdir(provenance_descriptor)))
            if names_after != names_before:
                raise ValueError(
                    "freeze provenance changed while it was being inspected"
                )
            current = os.stat(
                "provenance",
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                _snapshot_entry_identity(os.fstat(provenance_descriptor))
                != _snapshot_entry_identity(provenance_opened)
                or _snapshot_entry_identity(current)
                != _snapshot_entry_identity(provenance_metadata)
            ):
                raise ValueError(
                    "freeze provenance changed while it was being inspected"
                )
        finally:
            os.close(provenance_descriptor)
    elif root_descriptor is None:
        provenance_root = freeze_root / "provenance"
        if not provenance_root.is_dir() or provenance_root.is_symlink():
            if root_extra_names:
                raise ValueError(
                    "freeze root contents mismatch: undeclared artifacts "
                    f"{sorted(root_extra_names)!r}"
                )
            return
        provenance_extra_names = {
            child.name for child in provenance_root.iterdir()
        } - {"freeze_human_eval_ratings.py", "build_human_eval_packet.py"}
        if provenance_extra_names:
            raise ValueError(
                "provenance archive contents mismatch: "
                f"undeclared artifacts {sorted(provenance_extra_names)!r}"
            )
    if root_extra_names:
        raise ValueError(
            "freeze root contents mismatch: undeclared artifacts "
            f"{sorted(root_extra_names)!r}"
        )


def _require_freeze_inventory_stable(
    freeze_root,
    descriptor,
    root_opened,
    names,
    metadata,
):
    try:
        current_names = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise ValueError("freeze root changed while it was being snapshotted") from exc
    if current_names != names:
        raise ValueError("freeze root changed while it was being snapshotted")
    if _snapshot_entry_identity(os.fstat(descriptor)) != _snapshot_entry_identity(
        root_opened
    ):
        raise ValueError("freeze root changed while it was being snapshotted")
    for name in names:
        try:
            current = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                f"freeze root {name} changed while it was being snapshotted"
            ) from exc
        if _snapshot_entry_identity(current) != _snapshot_entry_identity(
            metadata[name]
        ):
            raise ValueError(
                f"freeze root {name} changed while it was being snapshotted"
            )
    _require_snapshot_directory_binding(
        freeze_root,
        descriptor,
        label="freeze root",
    )


def _snapshot_directory_inventory(
    source_root,
    descriptor,
    *,
    label,
    parent_descriptor=None,
    entry_name=None,
):
    """Capture a stable recursive inode/metadata inventory without file bytes."""
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        raise ValueError(f"{label} must be a regular directory: {source_root}")
    try:
        names = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise ValueError(f"{label} could not be enumerated: {source_root}") from exc

    metadata = {}
    for name in names:
        try:
            metadata[name] = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                f"{label} {name} changed while it was being snapshotted"
            ) from exc

    entries = []
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    for name in names:
        child_label = f"{label} {name}"
        child_metadata = metadata[name]
        child_identity = _snapshot_entry_identity(child_metadata)
        if stat.S_ISDIR(child_metadata.st_mode):
            try:
                child_descriptor = os.open(name, directory_flags, dir_fd=descriptor)
            except OSError as exc:
                raise ValueError(
                    f"{child_label} changed while it was being snapshotted"
                ) from exc
            try:
                child_opened = os.fstat(child_descriptor)
                if _snapshot_entry_identity(child_opened) != child_identity:
                    raise ValueError(
                        f"{child_label} changed while it was being snapshotted"
                    )
                child_inventory = _snapshot_directory_inventory(
                    Path(source_root) / name,
                    child_descriptor,
                    label=child_label,
                    parent_descriptor=descriptor,
                    entry_name=name,
                )
            finally:
                os.close(child_descriptor)
            entries.append((name, "directory", child_identity, child_inventory))
        elif stat.S_ISREG(child_metadata.st_mode):
            entries.append((name, "file", child_identity))
        else:
            raise ValueError(
                f"{child_label} must be a regular file or directory: "
                f"{Path(source_root) / name}"
            )

    try:
        names_after = tuple(sorted(os.listdir(descriptor)))
    except OSError as exc:
        raise ValueError(f"{label} changed while it was being snapshotted") from exc
    if names_after != names or _snapshot_entry_identity(
        os.fstat(descriptor)
    ) != _snapshot_entry_identity(opened):
        raise ValueError(f"{label} changed while it was being snapshotted")
    for name in names:
        try:
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise ValueError(
                f"{label} {name} changed while it was being snapshotted"
            ) from exc
        if _snapshot_entry_identity(current) != _snapshot_entry_identity(metadata[name]):
            raise ValueError(
                f"{label} {name} changed while it was being snapshotted"
            )

    if parent_descriptor is None:
        _require_snapshot_directory_binding(source_root, descriptor, label=label)
    else:
        try:
            current = os.stat(
                entry_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(f"{label} changed while it was being snapshotted") from exc
        if (
            not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValueError(f"{label} changed while it was being snapshotted")
    return (_snapshot_entry_identity(opened), tuple(entries))


def _snapshot_freeze_tree(freeze_root, blind_freeze):
    """Capture every allowed freeze artifact from one bound root generation."""
    freeze_root = Path(freeze_root)
    blind_freeze = Path(blind_freeze)
    descriptor = _open_snapshot_directory(freeze_root, label="freeze root")
    try:
        root_opened = os.fstat(descriptor)
        try:
            names = tuple(sorted(os.listdir(descriptor)))
        except OSError as exc:
            raise ValueError(
                f"freeze root could not be enumerated: {freeze_root}"
            ) from exc
        metadata = {}
        for name in names:
            try:
                metadata[name] = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise ValueError(
                    f"freeze root {name} changed while it was being snapshotted"
                ) from exc
        _reject_undeclared_freeze_sidecars(
            freeze_root,
            observed_names=names,
            observed_metadata=metadata,
            root_descriptor=descriptor,
        )
        _require_freeze_inventory_stable(
            freeze_root,
            descriptor,
            root_opened,
            names,
            metadata,
        )
        recursive_inventory = _snapshot_directory_inventory(
            freeze_root,
            descriptor,
            label="freeze root",
        )
        _require_freeze_inventory_stable(
            freeze_root,
            descriptor,
            root_opened,
            names,
            metadata,
        )
        _snapshot_directory_descriptor(
            freeze_root,
            blind_freeze,
            descriptor,
            label="freeze root",
        )
        _require_freeze_inventory_stable(
            freeze_root,
            descriptor,
            root_opened,
            names,
            metadata,
        )
        if _snapshot_directory_inventory(
            freeze_root,
            descriptor,
            label="freeze root",
        ) != recursive_inventory:
            raise ValueError("freeze root changed while it was being snapshotted")
        _require_freeze_inventory_stable(
            freeze_root,
            descriptor,
            root_opened,
            names,
            metadata,
        )
    finally:
        os.close(descriptor)


def score(row, field):
    value = str(row.get(field) or "").strip()
    return int(value) if value else None


def _percentile(sorted_values, q):
    if not sorted_values:
        raise ValueError("percentile requires values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    weight = pos - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def _bootstrap_mean_ci(diffs, *, seed):
    rng = random.Random(seed)
    n = len(diffs)
    draws = [
        statistics.mean([diffs[rng.randrange(n)] for _ in range(n)])
        for _ in range(BOOTSTRAP_DRAWS)
    ]
    draws.sort()
    return [_percentile(draws, 0.025), _percentile(draws, 0.975)]


def _paired_summary(left, right, *, seed):
    if len(left) != len(right) or not left:
        raise ValueError("paired vectors must be non-empty and equal length")
    diffs = [b - a for a, b in zip(left, right)]
    sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    return {
        "n_pairs": len(diffs),
        "left_mean": statistics.mean(left),
        "right_mean": statistics.mean(right),
        "mean_difference": statistics.mean(diffs),
        "median_difference": statistics.median(diffs),
        "bootstrap_95pct_ci_mean_difference": _bootstrap_mean_ci(diffs, seed=seed),
        "paired_dz": (statistics.mean(diffs) / sd) if sd > 0 else None,
        "positive_tasks": sum(d > 0 for d in diffs),
        "negative_tasks": sum(d < 0 for d in diffs),
        "tied_tasks": sum(d == 0 for d in diffs),
        "task_differences": diffs,
    }


def report_scores(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["blind_id"], []).append(row)
    scores, counts = {}, {}
    for blind_id, items in grouped.items():
        for field in DIMS:
            values = [v for v in (score(row, field) for row in items) if v is not None]
            scores[(blind_id, field)] = statistics.mean(values) if values else None
            counts[(blind_id, field)] = len(values)
    return scores, counts


def _empty_pair():
    return {
        "n_pairs": 0,
        "left_mean": None,
        "right_mean": None,
        "mean_difference": None,
        "median_difference": None,
        "bootstrap_95pct_ci_mean_difference": None,
        "paired_dz": None,
        "positive_tasks": 0,
        "negative_tasks": 0,
        "tied_tasks": 0,
        "task_differences": {},
    }


def analyze(
    rating_paths,
    *,
    freeze_root=FREEZE_ROOT,
    packet_root=PACKET_ROOT,
    packet_path=freeze.DEFAULT_PACKET,
    protocol_path=freeze.DEFAULT_PROTOCOL,
    assignment_plan_path=freeze.DEFAULT_ASSIGNMENT_PLAN,
    annotator_guide_path=freeze.DEFAULT_ANNOTATOR_GUIDE,
    analysis_plan_path=PLAN,
    task_manifest_path=TASKS,
    repo_root=ROOT,
):
    """Verify captured blinded bytes first, then capture and verify treatment identity."""
    rating_paths = [Path(path) for path in rating_paths]
    freeze_root = Path(freeze_root)
    packet_root = Path(packet_root)
    packet_path = Path(packet_path)
    protocol_path = Path(protocol_path)
    assignment_plan_path = Path(assignment_plan_path)
    annotator_guide_path = Path(annotator_guide_path)
    analysis_plan_path = Path(analysis_plan_path)
    task_manifest_path = Path(task_manifest_path)
    repo_root = Path(repo_root)

    if freeze_root.is_symlink() or not freeze_root.is_dir():
        raise ValueError(f"freeze root must be a regular directory: {freeze_root}")
    if packet_root.is_symlink() or not packet_root.is_dir():
        raise ValueError(f"human-evaluation output root must be a regular directory: {packet_root}")

    with tempfile.TemporaryDirectory(prefix="vera-human-analysis-") as scratch_name:
        scratch = Path(scratch_name)

        # Capture the blinded side before any verifier is called. Human scores,
        # agreement, packet IDs, and frozen provenance below are the exact bytes
        # that both verification and analysis will use.
        blind_root = scratch / "blinded"
        blind_freeze = blind_root / "freeze"
        blind_packet = _snapshot_file(
            packet_path,
            blind_root / "packet" / packet_path.name,
            label="blinded packet",
        )
        blind_protocol = _snapshot_file(
            protocol_path,
            blind_root / "protocol" / protocol_path.name,
            label="human-evaluation protocol",
        )
        blind_assignment = _snapshot_file(
            assignment_plan_path,
            blind_root / "assignment" / assignment_plan_path.name,
            label="human-evaluation assignment plan",
        )
        blind_annotator_guide = _snapshot_file(
            annotator_guide_path,
            blind_root / "annotator_guide" / annotator_guide_path.name,
            label="human-evaluation annotator guide",
        )
        freeze._verify_frozen_governing_documents(
            blind_protocol.read_bytes(),
            blind_assignment.read_bytes(),
            blind_annotator_guide.read_bytes(),
        )
        blind_analysis_plan = _snapshot_file(
            analysis_plan_path,
            blind_root / "analysis_plan" / analysis_plan_path.name,
            label="human-evaluation analysis plan",
        )
        analysis_plan_sha256 = hashlib.sha256(blind_analysis_plan.read_bytes()).hexdigest()
        if analysis_plan_sha256 != FROZEN_ANALYSIS_PLAN_SHA256:
            raise ValueError(
                "frozen analysis plan fingerprint mismatch: "
                f"expected {FROZEN_ANALYSIS_PLAN_SHA256}, got {analysis_plan_sha256}"
            )
        # Capture the complete blinded freeze through one retained root
        # descriptor. Core files and every optional archive therefore come
        # from the same directory generation, and the independent verifier
        # sees the complete allowed artifact set rather than a path-by-path
        # mixture assembled across replacement windows.
        _snapshot_freeze_tree(freeze_root, blind_freeze)
        blind_rating_paths = _snapshot_raw_ratings(rating_paths, blind_root / "raw_ratings")

        blinded = blind_verify.verify_frozen_snapshot(
            blind_rating_paths,
            freeze_root=blind_freeze,
            packet_path=blind_packet,
            protocol_path=blind_protocol,
            assignment_plan_path=blind_assignment,
            annotator_guide_path=blind_annotator_guide,
        )
        if (
            blinded.get("n_annotators") != 2
            or blinded.get("requires_predeclared_multi_rater_statistic")
        ):
            raise ValueError("analysis plan requires exactly two annotators before unblinding")

        # Only after the blinded gate passes may treatment identity be read.
        mapping_root = scratch / "mapping"
        mapping_root.mkdir(parents=True)
        mapping_packet = mapping_root / "packet.jsonl"
        mapping_packet.write_bytes(blind_packet.read_bytes())
        mapping_manifest = _snapshot_file(
            packet_root / "manifest.json",
            mapping_root / "manifest.json",
            label="human-evaluation packet manifest",
        )
        mapping_key = _snapshot_file(
            packet_root / "blinding_key.csv",
            mapping_root / "blinding_key.csv",
            label="coordinator blinding key",
        )
        _snapshot_file(
            packet_root / "ratings_template.csv",
            mapping_root / "ratings_template.csv",
            label="human-evaluation ratings template",
        )
        mapping_tasks = _snapshot_file(
            task_manifest_path,
            scratch / "task_manifest" / task_manifest_path.name,
            label="frozen task manifest",
        )

        mapped = map_verify.verify_packet(
            output_root=mapping_root,
            task_manifest_path=mapping_tasks,
            repo_root=repo_root,
        )

        manifest = packet._load_task_manifest(mapping_tasks)
        tasks = sorted(manifest["tasks"])
        blind_ids = freeze._packet_blind_ids(blind_packet)
        frozen_ratings_path = blind_freeze / "frozen_ratings.csv"
        rows, _ = freeze._load_ratings(
            [frozen_ratings_path],
            allowed_blind_ids=set(blind_ids),
        )
        map_rows = map_verify._read_csv(
            mapping_key.read_bytes(),
            fields=map_verify.KEY_FIELDS,
            label="blinding_key.csv",
        )
        mapping = {row["blind_id"].strip(): row for row in map_rows}
        if set(mapping) != set(blind_ids) or {row["blind_id"] for row in rows} != set(blind_ids):
            raise ValueError("blind-ID coverage mismatch")

        cells = {
            (row["variant_id"].strip(), row["task_id"].strip()): row["blind_id"].strip()
            for row in map_rows
        }
        if set(cells) != {(variant, task_id) for variant in VARIANTS for task_id in tasks}:
            raise ValueError("incomplete treatment/task mapping")

        scores, counts = report_scores(rows)
        variant_of = {
            blind_id: row["variant_id"].strip()
            for blind_id, row in mapping.items()
        }
        summaries = {}
        for variant in VARIANTS:
            summaries[variant] = {}
            for field in DIMS:
                observed = [scores[(cells[(variant, task_id)], field)] for task_id in tasks]
                observed = [value for value in observed if value is not None]
                dist = {str(i): 0 for i in range(1, 6)}
                for row in rows:
                    value = score(row, field)
                    if variant_of[row["blind_id"]] == variant and value is not None:
                        dist[str(value)] += 1
                summaries[variant][field] = {
                    "n_reports_total": len(tasks),
                    "n_reports_scored": len(observed),
                    "n_raw_scores": sum(
                        counts[(cells[(variant, task_id)], field)]
                        for task_id in tasks
                    ),
                    "mean_report_score": statistics.mean(observed) if observed else None,
                    "median_report_score": statistics.median(observed) if observed else None,
                    "raw_score_distribution": dist,
                }

        contrasts = {}
        for contrast_index, (left, right, name) in enumerate(CONTRASTS):
            contrasts[name] = {}
            for dimension_index, field in enumerate(DIMS):
                complete = [
                    task_id
                    for task_id in tasks
                    if scores[(cells[(left, task_id)], field)] is not None
                    and scores[(cells[(right, task_id)], field)] is not None
                ]
                if complete:
                    result = _paired_summary(
                        [scores[(cells[(left, task_id)], field)] for task_id in complete],
                        [scores[(cells[(right, task_id)], field)] for task_id in complete],
                        seed=SEED + contrast_index * 100 + dimension_index,
                    )
                    result["task_differences"] = dict(
                        zip(complete, result["task_differences"])
                    )
                else:
                    result = _empty_pair()
                result["task_ids_included"] = complete
                result["missing_pair_tasks"] = [
                    task_id for task_id in tasks if task_id not in complete
                ]
                contrasts[name][field] = result

        agreement_path = blind_freeze / "agreement.json"
        agreement = json.loads(agreement_path.read_text(encoding="utf-8"))
        provenance = {
            name: fingerprint(path)
            for name, path in {
                "analysis_plan": blind_analysis_plan,
                "task_manifest": mapping_tasks,
                "packet_manifest": mapping_manifest,
                "treatment_mapping": mapping_key,
                "freeze_manifest": blind_freeze / "freeze_manifest.json",
                "frozen_ratings": frozen_ratings_path,
                "pre_unblinding_agreement": agreement_path,
            }.items()
        }
        provenance.update(
            {
                "protocol": fingerprint(
                    blind_protocol,
                    logical_path="paper/HUMAN_EVAL_PROTOCOL.md",
                ),
                "assignment_plan": fingerprint(
                    blind_assignment,
                    logical_path="paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
                ),
                "annotator_guide": fingerprint(
                    blind_annotator_guide,
                    logical_path="paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
                ),
            }
        )

        return {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "task_set_id": manifest["task_set_id"],
            "status": "human_validation_analysis",
            "analysis_scope": "complementary_not_main_confirmatory",
            "human_ratings_generated": False,
            "treatment_outputs_rerun": False,
            "n_tasks": len(tasks),
            "task_ids": tasks,
            "variants": list(VARIANTS),
            "dimensions": list(DIMS),
            "report_score_aggregation": "mean_observed_rater_scores_per_report_dimension",
            "bootstrap_seed": SEED,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "hypothesis_tests": "none_predeclared_for_human_validation",
            "verification": {
                "blinded_freeze": blinded,
                "packet_and_mapping": mapped,
                "analysis_inputs_snapshot_bound": True,
            },
            "provenance": provenance,
            "pre_unblinding_agreement": agreement,
            "variant_summary": summaries,
            "paired_contrasts": contrasts,
        }
