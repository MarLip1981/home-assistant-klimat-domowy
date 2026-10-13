"""Pure pollen-state parsing helpers used by the climate decision engine."""

from __future__ import annotations

from typing import Any


_MISSING = {"", "unknown", "unavailable", "none", "n/a", "not available", "no data"}


def text(value: Any) -> str:
    """Normalize text states without changing their meaning."""
    if value is None:
        return ""
    return str(value).strip().lower().replace("_", " ").replace("-", " ")


def number(value: Any) -> float | None:
    """Parse a finite number safely."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def is_none_detected(value: Any) -> bool:
    """Recognize the source integration's explicit 'no pollen detected' state."""
    normalized = text(value)
    return normalized in {
        "brak",
        "no pollen",
        "no pollen detected",
        "none detected",
        "brak wykrytych pylkow",
        "brak wykrytych pyłków",
        "nie wykryto pylkow",
        "nie wykryto pyłków",
    }


def is_high(value: Any) -> bool:
    """Recognize common text and numeric high-risk levels."""
    normalized = text(value)
    if not normalized:
        return False
    if any(word in normalized for word in ("very high", "extreme", "severe", "bardzo wysok", "wysok")):
        return True
    numeric = number(normalized)
    return numeric is not None and numeric >= 4


def is_low(value: Any) -> bool:
    """Recognize an explicit low pollen-risk state."""
    return text(value) in {"low", "very low", "niski", "niskie", "niskiego", "bardzo niski"}


def is_present(value: Any) -> bool:
    """Recognize numeric non-zero values and explicit moderate/high pollen levels."""
    normalized = text(value)
    if not normalized or is_none_detected(value) or is_low(value):
        return False
    numeric = number(normalized)
    if numeric is not None:
        return numeric > 0
    return any(
        word in normalized
        for word in ("moderate", "medium", "umiark", "high", "very high", "wysok")
    )


def is_known(value: Any) -> bool:
    """Return whether the source state is interpretable, not merely non-empty."""
    normalized = text(value)
    if normalized in _MISSING:
        return False
    return (
        is_none_detected(value)
        or is_high(value)
        or is_low(value)
        or is_present(value)
        or number(normalized) is not None
    )
