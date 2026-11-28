"""Fail-closed parser regressions for read-only research audit workflows.

Synthetic YAML only: these tests never execute treatments or evaluators.
"""
import pytest
import yaml

from scripts.audit_workflow_read_only import assert_read_only_workflow_steps


BASE = """name: synthetic-archive-audit
on:
  push:
    paths:
      - scripts/run_budget_main_study.py
jobs:
  audit:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@pinned
        with:
          persist-credentials: false
      - run: echo verified
"""


@pytest.mark.parametrize(
    "mutant",
    (
        # GitHub/other YAML parsers need not resolve duplicate mappings like
        # PyYAML's permissive BaseLoader. The local audit must reject them.
        BASE + """jobs:
  audit:
    runs-on: ubuntu-24.04
    steps:
      - run: echo verified
""",
        BASE.replace(
            "      - run: echo verified\n",
            "      - run: python -m scripts.run_budget_main_study\n"
            "        run: echo verified\n",
        ),
        BASE.replace(
            "      - uses: actions/checkout@pinned\n",
            "      - uses: python -m scripts.run_pilot\n"
            "        uses: actions/checkout@pinned\n",
        ),
        BASE.replace(
            "    runs-on: ubuntu-24.04\n",
            "    env:\n      AUDIT_CMD: python -m scripts.run_pilot\n"
            "    env:\n      AUDIT_CMD: echo verified\n"
            "    runs-on: ubuntu-24.04\n",
        ),
        BASE.replace(
            "          persist-credentials: false\n",
            "          persist-credentials: python -m scripts.evaluate_posthoc_support\n"
            "          persist-credentials: false\n",
        ),
        BASE.replace(
            "jobs:\n",
            'defaults:\n  run:\n    shell: bash -c "python -m scripts.run_pilot; bash {0}"\n'
            "    shell: bash\njobs:\n",
        ),
        BASE.replace(
            "      - scripts/run_budget_main_study.py\n",
            "      - scripts/run_budget_main_study.py\n"
            "    paths:\n      - README.md\n",
        ),
        BASE.replace(
            "      - run: echo verified\n",
            "      - \"run\": python -m scripts.run_budget_main_study\n"
            "        run: echo verified\n",
        ),
    ),
)
def test_duplicate_yaml_mapping_keys_fail_closed(mutant):
    # The old parser accepts these documents with a silent last-key-wins
    # mapping; a successful read-only verdict must not depend on that choice.
    assert isinstance(yaml.load(mutant, Loader=yaml.BaseLoader), dict)
    with pytest.raises(AssertionError, match="duplicate YAML mapping key"):
        assert_read_only_workflow_steps(mutant)


def test_unique_keys_and_source_watch_are_still_accepted():
    assert_read_only_workflow_steps(BASE)
