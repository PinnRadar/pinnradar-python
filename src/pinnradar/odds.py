"""Odds helpers: implied probability, margin and no-vig (fair) prices for decimal odds."""

from __future__ import annotations

from typing import List, Sequence


def implied(price: float) -> float:
    """Implied probability of a decimal price (1 / price)."""
    if price <= 1:
        raise ValueError("decimal odds must be greater than 1")
    return 1.0 / price


def margin(prices: Sequence[float]) -> float:
    """Bookmaker margin of a complete market: sum of implied probabilities minus 1."""
    return sum(implied(p) for p in prices) - 1.0


def no_vig(prices: Sequence[float], method: str = "multiplicative") -> List[float]:
    """Fair (no-vig) decimal prices for a complete market (every outcome).

    `method` is "multiplicative" (proportional, the usual default) or "power" (takes more
    margin from longshots).

    >>> [round(x, 3) for x in no_vig([1.952, 1.952])]
    [2.0, 2.0]
    """
    if len(prices) < 2:
        raise ValueError("need every outcome of the market (at least two prices)")
    q = [implied(p) for p in prices]
    if method == "multiplicative":
        s = sum(q)
        probs = [x / s for x in q]
    elif method == "power":
        lo, hi = 0.05, 50.0
        for _ in range(200):
            k = (lo + hi) / 2
            if sum(x ** k for x in q) > 1:
                lo = k
            else:
                hi = k
        k = (lo + hi) / 2
        probs = [x ** k for x in q]
        t = sum(probs)
        probs = [p / t for p in probs]
    else:
        raise ValueError("method must be 'multiplicative' or 'power'")
    return [1.0 / p for p in probs]
