"""Turn independent worker answers into one answer plus the dissent it outvoted.

Deterministic on purpose: the same batch always yields the same verdict, so a run can be replayed
and audited. Text comparison normalises case and whitespace only; it does not try to be clever
about meaning, because a silent semantic merge would hide a real disagreement.
"""

from __future__ import annotations

from typing import Any


def _normalise(text: Any) -> str:
    return " ".join(str(text).split()).lower()


def vote(results: list[dict], key: str = "text") -> dict[str, Any]:
    counts: dict[str, int] = {}
    originals: dict[str, str] = {}
    order: list[str] = []
    for result in results:
        value = result.get(key)
        if value is None:
            continue
        normalised = _normalise(value)
        if normalised not in counts:
            counts[normalised] = 0
            originals[normalised] = str(value).strip()
            order.append(normalised)
        counts[normalised] += 1

    if not counts:
        return {"winner": None, "support": 0, "agreement": 0.0, "dissent": []}

    total = sum(counts.values())
    winner = max(order, key=lambda item: (counts[item], -order.index(item)))
    return {
        "winner": originals[winner],
        "support": counts[winner],
        "agreement": round(counts[winner] / total, 4),
        "dissent": [originals[item] for item in order if item != winner],
    }


def rank(results: list[dict], key: str = "score") -> list[dict]:
    """Highest score first; equal scores keep the order the workers finished in."""
    return sorted(results, key=lambda item: -float(item.get(key) or 0.0))


def merge(results: list[dict], strategy: str = "best", key: str = "text") -> dict:
    if not results:
        raise ValueError("merge needs at least one result")
    if strategy == "best":
        return rank(results)[0]
    if strategy == "vote":
        verdict = vote(results, key=key)
        for result in results:
            if str(result.get(key, "")).strip() == verdict["winner"]:
                return {**result, "consensus": verdict}
        return {**results[0], "consensus": verdict}
    raise ValueError(f"unknown merge strategy: {strategy}")
