"""Outcome-free synthetic integrity checks for historical factor source audit."""
from __future__ import annotations

import pytest

from scripts import audit_historical_variant_factors as audit


CONFIG = b'''class ExperimentConfig:
    @classmethod
    def from_variant(cls, variant_id):
        variants = {
            "D3": cls(variant_id="D3", planning_mode="direct", source_budget=3, verification_mode="none", stream_report=False),
            "D6": cls(variant_id="D6", planning_mode="direct", source_budget=6, verification_mode="none", stream_report=False),
            "P6": cls(variant_id="P6", planning_mode="planner", source_budget=6, verification_mode="none", stream_report=False),
            "P6V": cls(variant_id="P6V", planning_mode="planner", source_budget=6, verification_mode="verify", stream_report=False),
        }
        try:
            return variants[variant_id.upper()]
        except KeyError:
            raise ValueError("unknown variant")
'''

RUNNER = b'''VARIANTS = ("D3", "D6", "P6", "P6V")
async def main():
    tasks = []
    for task in tasks:
        for variant_id in VARIANTS:
            base_config = ExperimentConfig.from_variant(variant_id)
            config = replace(base_config, task_set_id=task_set_id, task_id=task["id"])
            await run_agent(task=task["question"], experiment_config=config)
'''


def test_literal_historical_mapping_is_source_bound():
    assert audit.inspect_variant_factory(CONFIG) == audit.EXPECTED_FACTORS


@pytest.mark.parametrize("mutated", [
    CONFIG.replace(b'source_budget=3', b'source_budget=6'),
    CONFIG.replace(b'planning_mode="planner"', b'planning_mode="direct"'),
    CONFIG.replace(b'verification_mode="verify"', b'verification_mode="none"'),
    CONFIG.replace(b'stream_report=False', b'stream_report=True'),
    CONFIG.replace(b'"P6V": cls(', b'"P6": cls('),
    CONFIG.replace(b'source_budget=3', b'source_budget=3 + 0'),
    CONFIG.replace(b'variant_id="D3"', b'variant_id="P6"'),
    CONFIG.replace(b'@classmethod', b'@staticmethod'),
    CONFIG.replace(b'return variants[variant_id.upper()]', b'return variants["D3"]'),
    CONFIG.replace(b'source_budget=3', b'source_budget=3, source_budget=3'),
    b'\xff',
])
def test_rejects_invalid_factor_source(mutated):
    with pytest.raises(audit.HistoricalFactorError):
        audit.inspect_variant_factory(mutated)


def test_runner_handoff_from_variant_to_agent():
    audit.inspect_runner_factor_handoff(RUNNER)


@pytest.mark.parametrize("mutated", [
    RUNNER.replace(b'ExperimentConfig.from_variant(variant_id)', b'ExperimentConfig.from_variant("D3")'),
    RUNNER.replace(b'experiment_config=config', b'experiment_config=base_config'),
    RUNNER.replace(b'config = replace(base_config', b'config = replace(other_config'),
    RUNNER.replace(b'base_config = ExperimentConfig', b'base_config = OtherConfig'),
    RUNNER.replace(b'await run_agent', b'run_agent'),
    RUNNER.replace(b'await run_agent', b'config = override\n            await run_agent'),
])
def test_runner_rejects_broken_factor_handoff(mutated):
    with pytest.raises((audit.HistoricalFactorError,
                        audit.design.HistoricalDesignSourceError)):
        audit.inspect_runner_factor_handoff(mutated)


def test_checkout_receipt_marks_all_scientific_boundaries_false(tmp_path, monkeypatch):
    monkeypatch.setattr(audit.design, 'audit_checkout', lambda _root: {
        'historical_runner_blob_sha': audit.design.RUNNER_BLOB_SHA,
    })
    def fake_git(root, *args):
        if args == ('rev-parse', f'{audit.HISTORICAL_RUNNER_COMMIT}:{audit.CONFIG_PATH}'):
            return (audit.CONFIG_BLOB_SHA + '\n').encode()
        if args == ('show', f'{audit.HISTORICAL_RUNNER_COMMIT}:{audit.CONFIG_PATH}'):
            return CONFIG
        if args == ('show', f'{audit.HISTORICAL_RUNNER_COMMIT}:{audit.design.RUNNER_PATH}'):
            return RUNNER
        raise AssertionError(args)
    monkeypatch.setattr(audit.design, '_git', fake_git)
    result = audit.audit_checkout(tmp_path)
    assert result['runner_config_handoff_ast_checked'] is True
    assert result['source_linked_factor_matrix'] == audit.EXPECTED_FACTORS
    assert result['historical_config_blob'] == audit.CONFIG_BLOB_SHA
    for field in ('original_treatment_execution_authenticated',
                  'original_report_trace_custody_authenticated',
                  'actual_factor_values_in_original_traces_verified',
                  'equal_total_compute_established', 'causal_effects_identified',
                  'human_validation_performed'):
        assert result[field] is False


def test_checkout_rejects_wrong_pinned_blob(tmp_path, monkeypatch):
    monkeypatch.setattr(audit.design, 'audit_checkout', lambda _root: {
        'historical_runner_blob_sha': audit.design.RUNNER_BLOB_SHA,
    })
    monkeypatch.setattr(audit.design, '_git', lambda *_a: b'0' * 40)
    with pytest.raises(audit.HistoricalFactorError, match='pinned identity'):
        audit.audit_checkout(tmp_path)
