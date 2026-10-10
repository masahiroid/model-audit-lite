"""Small statistics helpers for judging probe results (pure Python, no SciPy).

Why: a probe set of n=60 gives a coarse measurement. A point estimate ("19/60 followed") hides a wide interval, and
"one more probe failed after conversion" is usually noise. These helpers put an interval on a rate, test a before/after
change on the *same* probes (paired), and say how large a change the probe set could even detect.
"""
from __future__ import annotations

import math

Z95 = 1.959964
Z80 = 0.841621  # one-sided z for 80% power


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n (better than the normal approximation for small n or extreme rates)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(regressions: int, improvements: int) -> float:
    """Two-sided exact McNemar test (sign test on discordant pairs).

    `regressions` = probes that were safe before and unsafe after; `improvements` = the reverse. Probes whose outcome did not
    change carry no information. Returns the p-value of "no systematic change"; 1.0 if there are no discordant pairs.
    """
    n = regressions + improvements
    if n == 0:
        return 1.0
    k = min(regressions, improvements)
    # P(X <= k) for X ~ Binomial(n, 1/2), doubled for two-sided
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def detectable_difference(n: int, p: float = 0.5, z_alpha: float = Z95, z_power: float = Z80) -> float:
    """Smallest difference between two independent rates measurable with n probes each (80% power, alpha=0.05, two-sided).

    A conservative guide: paired designs (same probes before/after) are usually more sensitive, but this tells you the order
    of magnitude of changes a probe set of size n can resolve. p=0.5 is the worst case.
    """
    if n <= 0:
        return 1.0
    return (z_alpha + z_power) * math.sqrt(2 * p * (1 - p) / n)


def format_rate(k: int, n: int) -> str:
    lo, hi = wilson_interval(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (95% CI {100 * lo:.0f}-{100 * hi:.0f}%)" if n else "0/0"
