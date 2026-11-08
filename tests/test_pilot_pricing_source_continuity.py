"""Synthetic checks: costed pilot summaries bind to frozen pricing source bytes.

No treatment/evaluator API calls or changes to frozen findings.
"""
from pathlib import Path
import os

import pytest

from scripts import summarize_pilot as pilot
from scripts.audit_pilot_cost_summary import FROZEN_PILOT_PRICING_SHA256


FROZEN = Path(__file__).resolve().parents[1] / "experiments" / "openai_pricing_2026-09-08.json"


def _price(tmp_path, monkeypatch):
    target = tmp_path / "pricing.json"
    target.write_bytes(FROZEN.read_bytes())
    monkeypatch.setattr(pilot, "PRICING_FILE", target)
    return target


def test_captures_one_pinned_frozen_price_generation(tmp_path, monkeypatch):
    _price(tmp_path, monkeypatch)
    payload, snapshot = pilot._capture_pilot_pricing()
    assert payload["unit"] == "per_1m_text_tokens"
    assert snapshot[1] == FROZEN_PILOT_PRICING_SHA256
    assert pilot._verify_pilot_pricing_snapshot(snapshot) is None
    assert pilot._load_pricing() == payload


def test_rejects_mutually_changed_rates_and_fingerprint(tmp_path, monkeypatch):
    path = _price(tmp_path, monkeypatch)
    path.write_bytes(path.read_bytes().replace(b'"input": 4.0', b'"input": 8.0', 1))
    with pytest.raises(ValueError, match="immutable SHA-256 pin"):
        pilot._capture_pilot_pricing()


def test_same_byte_price_path_replacement_invalidates_identity(tmp_path, monkeypatch):
    path = _price(tmp_path, monkeypatch)
    _, snapshot = pilot._capture_pilot_pricing()
    replacement = tmp_path / "outside-roster.json"
    replacement.write_bytes(path.read_bytes())
    os.replace(replacement, path)
    with pytest.raises(ValueError, match="identity changed before publication"):
        pilot._verify_pilot_pricing_snapshot(snapshot)


def test_oversized_price_rejected_before_json_parse(tmp_path, monkeypatch):
    path = _price(tmp_path, monkeypatch)
    path.write_bytes(b" " * (pilot.MAX_PILOT_PRICING_JSON_BYTES + 1))
    with pytest.raises(ValueError, match="64 KiB limit"):
        pilot._capture_pilot_pricing()


def test_aliasing_frozen_prices_is_rejected(tmp_path, monkeypatch):
    path = _price(tmp_path, monkeypatch)
    os.link(path, tmp_path / "other.json")
    with pytest.raises(ValueError, match="single-link regular file"):
        pilot._capture_pilot_pricing()


def test_symlinked_frozen_price_is_rejected(tmp_path, monkeypatch):
    path = _price(tmp_path, monkeypatch)
    target = tmp_path / "outside.json"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(ValueError, match="invalid frozen pricing document"):
        pilot._capture_pilot_pricing()


def test_price_mutation_during_summary_stops_both_publications(tmp_path, monkeypatch):
    from tests.test_pilot_summary_source_continuity import _setup
    _setup(tmp_path, monkeypatch)
    original = pilot._load_traces

    def mutate_after_costing(pricing, *, source_snapshot=None):
        rows = original(pricing, source_snapshot=source_snapshot)
        pilot.PRICING_FILE.write_bytes(pilot.PRICING_FILE.read_bytes() + b" ")
        return rows

    monkeypatch.setattr(pilot, "_load_traces", mutate_after_costing)
    with pytest.raises(ValueError, match="pricing"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()


def test_price_mutation_after_first_output_rolls_back_only_owned_json(
    tmp_path, monkeypatch,
):
    from tests.test_pilot_summary_source_continuity import _setup
    _setup(tmp_path, monkeypatch)
    original_link = os.link

    def mutate_after_first_link(source, target, *args, **kwargs):
        result = original_link(source, target, *args, **kwargs)
        if Path(target) == pilot.OUTPUT_JSON:
            pilot.PRICING_FILE.write_bytes(pilot.PRICING_FILE.read_bytes() + b" ")
        return result

    monkeypatch.setattr(pilot.os, "link", mutate_after_first_link)
    with pytest.raises(ValueError, match="pricing"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()
    assert not list(tmp_path.glob(".pilot-publication-*.tmp"))
