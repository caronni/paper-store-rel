# holo2 internal tests

Tests here import `holo2` only (the firewall applies to tests inside
the tree too — no `holo`/`paperholo` imports, and `test_firewall.py`
walks this directory as well as `holo2/src`, so the rule is enforced
rather than merely written down here). Cross-implementation comparison
and qualification oracles live at repo root in `tests/holo2_oracles/`,
which may import both packages. The five-verdict gate that replaced the
old decode batteries lives in `holo2/measure/verdicts/`; the batteries
themselves were deleted with the measure cleanup — history has the
driver.

Collected by the repo suite once workplan item H0 wires
`holo2/src` onto the pytest pythonpath.

The tree mirrors the package tree: `core/`, `format/`, `capture/`,
`solve/`, `engine/`, `diag/` hold that package's tests and obey the same
dependency DAG (`test_layering.py`). Top level holds the cross-cutting
tier — conventions, firewall, layering, surfaces, the R0 move proof, the
CLI surface, shared fixtures in `conftest.py` — plus `_bench_*.py`
benches, which pytest does not collect.
