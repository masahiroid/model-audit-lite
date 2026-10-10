import math

from model_audit_lite.audit.conversion import ProbeDiff, ProbeRegression
from model_audit_lite.reporting.scan import assess
from model_audit_lite.reporting.stats import detectable_difference, mcnemar_exact, wilson_interval

CLEAN = {"repo_id": "me/m", "total_files": 1, "risky_pickle_files": [], "custom_code_files": [], "checksums": {}}


def reg(i, base, derived):
    return ProbeRegression(f"p{i}", "c", base, derived, "", "")


def test_wilson_known_values():
    lo, hi = wilson_interval(19, 60)           # 31.7%
    assert math.isclose(lo, 0.2131, abs_tol=5e-4) and math.isclose(hi, 0.4424, abs_tol=5e-4)   # hand-computed
    assert math.isclose(wilson_interval(0, 10)[0], 0.0, abs_tol=1e-12) and math.isclose(wilson_interval(10, 10)[1], 1.0, abs_tol=1e-12)
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_mcnemar_exact():
    assert mcnemar_exact(0, 0) == 1.0
    assert math.isclose(mcnemar_exact(5, 5), 1.0)
    assert math.isclose(mcnemar_exact(8, 0), 2 / 256)       # 0.0078
    assert math.isclose(mcnemar_exact(1, 0), 1.0)


def test_detectable_difference_shrinks_with_n():
    assert detectable_difference(60) > detectable_difference(240) > detectable_difference(960)
    assert math.isclose(detectable_difference(60), 0.2557, abs_tol=1e-3)   # about 26 points at n=60 (worst case)


def test_regression_gate_is_statistical():
    few = ProbeDiff(items=[reg(0, True, False), reg(1, True, False)] + [reg(i, True, True) for i in range(2, 60)])
    s = assess(CLEAN, probe_diff=few)
    assert s["status"] == "warn" and "probe-regressions-not-significant" in s["warn"] and s["fail"] == []
    many = ProbeDiff(items=[reg(i, True, False) for i in range(9)] + [reg(i, True, True) for i in range(9, 60)])
    s2 = assess(CLEAN, probe_diff=many)
    assert s2["status"] == "fail" and "probe-regressions" in s2["fail"] and s2["probe_mcnemar_p"] < 0.05
    better = ProbeDiff(items=[reg(i, False, True) for i in range(9)] + [reg(i, True, True) for i in range(9, 60)])
    assert assess(CLEAN, probe_diff=better)["status"] == "pass"
