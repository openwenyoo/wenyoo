"""
Helpers for normalizing LLM provider usage metrics.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


def now_ms() -> float:
    """Return a high-resolution timestamp in milliseconds."""
    return time.perf_counter() * 1000.0


def build_llm_metrics(
    *,
    provider: str,
    model: str,
    operation: str,
    started_at_ms: float,
    usage: Optional[Any] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize usage metadata from heterogeneous providers."""
    usage_dict = _usage_to_dict(usage)
    metrics: Dict[str, Any] = {
        "provider": provider,
        "model": model,
        "operation": operation,
        "latency_ms": round(time.perf_counter() * 1000.0 - started_at_ms, 2),
        "stream": False,
        "tools": False,
        "input_tokens": _first_number(
            usage_dict,
            "input_tokens",
            "prompt_tokens",
            "prompt_eval_count",
        ),
        "output_tokens": _first_number(
            usage_dict,
            "output_tokens",
            "completion_tokens",
            "eval_count",
        ),
        "cache_write_tokens": _first_number(
            usage_dict,
            "cache_creation_input_tokens",
        ),
        "cache_read_tokens": _first_number(
            usage_dict,
            "cache_read_input_tokens",
        ),
        "total_tokens": _first_number(
            usage_dict,
            "total_tokens",
        ),
    }
    if extra:
        metrics.update(extra)
    return metrics


def compact_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Drop unset values before logging."""
    return {key: value for key, value in metrics.items() if value is not None}


def _usage_to_dict(usage: Optional[Any]) -> Dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if hasattr(usage, "dict"):
        return usage.dict()
    return {
        key: getattr(usage, key)
        for key in dir(usage)
        if not key.startswith("_") and not callable(getattr(usage, key))
    }


def _first_number(data: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
    return None
