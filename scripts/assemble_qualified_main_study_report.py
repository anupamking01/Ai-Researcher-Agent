"""Read-only assembly of the qualified, historically frozen VERA inference report.

Use this for manuscript-facing excerpts: it places the required limitations
BEFORE the unchanged, historically published Markdown. The program neither
runs the experiment/evaluator nor recomputes effect estimates or human ratings.
The resulting text is a NONCANONICAL reading copy, not a new result.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

from scripts.verify_main_study_outputs import verify_outputs
from scripts.verify_published_main_study_inputs import verify_published_frozen_inputs

ROOT = Path(__file__).resolve().parents[1]
COVER = Path("paper/MAIN_STUDY_REPORTING_COVER.md")
HISTORICAL = Path("paper/MAIN_STUDY_INFERENCE.md")
MAX_MARKDOWN_BYTES = 256 * 1024
# Fixed output SHA-256s retained in the historical canonical-analysis archive
# checkout verification (artifact 10837878458). This anchors the *results*
# separately from the published CSV input aggregate.
CANONICAL_INFERENCE = Path("outputs/main_study_inference.json")
ORIGINAL_JSON_SHA256 = "bbf439aabf0db38afd5430a885aff107014c6b924c05c62d6d724d16e00f450f"
ORIGINAL_MARKDOWN_SHA256 = "9356cbad9711012850baef349c7d16a104d63987e1d7be2e53184456a8cb2f1c"
# Lock the entire *reviewed qualification*, not only a few searchable phrases.
# This is a repository-local reporting safety pin, NOT an independent archive
# attestation. Deliberate disclosure revisions require reviewing the complete
# replacement cover and updating this digest together.
REVIEWED_REPORTING_COVER_SHA256 = "a1705941a5834ab391a75f063e5ce10c08617ae2e040cfa90292b4df6b248b2e"
REQUIRED_QUALIFICATIONS = (
    "prospective precollection statistical preregistration is not established",
    "outcome blinding at the september 14 freeze is not established",
    "fixed-order temporal confounding",
    "not justified by the design as a randomization test",
    "exchangeability",
    "paired-bootstrap confidence intervals",
    "human validation remains pending",
    "original 40 treatment reports and traces are not independently authenticated",
)


def _capture_markdown(path: Path) -> bytes:
    """Read one bounded, stable regular document; refuse redirected leaf files."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"reporting source missing or unsafe: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_MARKDOWN_BYTES
        ):
            raise ValueError(f"reporting source is not a bounded regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            raw = source.read(MAX_MARKDOWN_BYTES + 1)
        after = os.fstat(descriptor)
        visible = os.stat(path, follow_symlinks=False)
        def identity(info: os.stat_result) -> tuple[int, ...]:
            return (
                info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            )
        if (
            len(raw) != before.st_size
            or identity(before) != identity(after)
            or identity(after) != identity(visible)
        ):
            raise ValueError(f"reporting source changed during capture: {path}")
        return raw
    except OSError as exc:
        raise ValueError(f"reporting source unreadable or changed: {path}") from exc
    finally:
        os.close(descriptor)


def _disclosure_text(cover: str) -> str:
    # Markdown emphasis is formatting, not evidence of an additional claim.
    plain = re.sub(r"[*_\x60]", "", cover)
    return " ".join(plain.casefold().split())


def assemble_qualified_report(*, repo_root: Path = ROOT) -> str:
    """Create a noncanonical reading copy only after existing source checks."""
    root = Path(repo_root)
    source = verify_published_frozen_inputs(repo_root=root)
    verify_outputs(root=root)
    report_bytes = _capture_markdown(root / HISTORICAL)
    json_bytes = _capture_markdown(root / CANONICAL_INFERENCE)
    cover_bytes = _capture_markdown(root / COVER)
    if (
        hashlib.sha256(report_bytes).hexdigest() != ORIGINAL_MARKDOWN_SHA256
        or hashlib.sha256(json_bytes).hexdigest() != ORIGINAL_JSON_SHA256
    ):
        raise ValueError("frozen canonical outputs differ from archived historical fingerprints")
    report = report_bytes.decode("utf-8")
    cover = cover_bytes.decode("utf-8")
    disclosures = _disclosure_text(cover)
    if any(phrase not in disclosures for phrase in REQUIRED_QUALIFICATIONS):
        raise ValueError("reporting cover is missing a required scientific limitation")
    if hashlib.sha256(cover_bytes).hexdigest() != REVIEWED_REPORTING_COVER_SHA256:
        raise ValueError("reporting cover differs from reviewed qualification fingerprint")
    # A second complete check and exact capture comparison reject observed
    # pathname/content substitution between verification and publication.
    verify_outputs(root=root)
    closing = verify_published_frozen_inputs(repo_root=root)
    if closing["verified_input_sha256"] != source["verified_input_sha256"]:
        raise ValueError("frozen CSV fingerprint changed during report assembly")
    if (
        _capture_markdown(root / HISTORICAL) != report_bytes
        or _capture_markdown(root / CANONICAL_INFERENCE) != json_bytes
        or _capture_markdown(root / COVER) != cover_bytes
    ):
        raise ValueError("reporting source changed before export")
    return (
        "# VERA main-study: qualified reporting copy (noncanonical)\n\n"
        "**Scope:** Automated historical estimates only. No randomized causal "
        "claim, independently preregistered confirmation, original report/trace "
        "authentication, or human-validation result is established.\n\n"
        "Original frozen report SHA-256: "
        + hashlib.sha256(report_bytes).hexdigest() + "\n\n"
        "Reporting cover SHA-256: "
        + hashlib.sha256(cover_bytes).hexdigest() + "\n\n"
        "Published frozen CSV aggregate SHA-256: "
        + source["published_aggregate_sha256"] + "\n\n"
        "The qualifications below govern all quoted estimates. Links copied "
        "from the sources remain relative to their original repository paths.\n\n"
        "## Mandatory methodological and provenance qualifications\n\n"
        + cover.rstrip() + "\n\n---\n\n"
        "## Original historically frozen inference (verbatim)\n\n"
        + report
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        text = assemble_qualified_report(repo_root=args.repo_root)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, f"qualified VERA reporting export blocked: {exc}\n")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
