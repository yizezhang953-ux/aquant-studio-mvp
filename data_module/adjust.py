"""Forward-adjust factors rebuilt from raw closes + corporate actions.

Recomputing over the WHOLE stored history (not one download window) keeps adj_factor continuous
when data is synced in several windows or updated incrementally.
"""
from __future__ import annotations

from typing import Iterable, Mapping


def factors_from_actions(days: list[str], closes: list[float], actions: Iterable[Mapping]) -> list[float]:
    """adj_factor per day (latest = 1): f[e-1] = f[e] * (P[e-1] - D) / (P[e-1] * (1 + B)).

    Multiple actions on one ex-date are combined; an action dated on a non-trading day applies to
    the next trading day.
    """
    by_day: dict[str, list[Mapping]] = {}
    for action in actions:
        by_day.setdefault(str(action["ex_date"])[:10], []).append(action)
    action_days = sorted(by_day)
    factors = [1.0] * len(days)
    pointer = len(action_days) - 1
    for i in range(len(days) - 1, 0, -1):
        factors[i - 1] = factors[i]
        cash = bonus = 0.0
        # actions with days[i-1] < ex_date <= days[i] take effect on days[i]
        while pointer >= 0 and action_days[pointer] > days[i - 1]:
            if action_days[pointer] <= days[i]:
                for action in by_day[action_days[pointer]]:
                    cash += float(action.get("cash_dividend") or 0)
                    bonus += float(action.get("bonus_ratio") or 0)
            pointer -= 1
        if cash or bonus:
            prev_close = closes[i - 1]
            ratio = (prev_close - cash) / (prev_close * (1 + bonus)) if prev_close else 1.0
            if 0 < ratio < 1:
                factors[i - 1] = factors[i] * ratio
    return [round(f, 8) for f in factors]
