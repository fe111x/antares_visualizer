from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Optional
import threading

from .data_access import (
    PLOT_DEFAULT_COLUMNS,
    _build_selection_signature,
    _load_selected_tables_cached,
    _load_selected_tables_pemmdb_type_aggregated_cached,
    _load_selected_tables_projected_cached,
    _load_selected_tables_tech_aggregated_cached,
    get_selector_hierarchy,
    load_trace_selector_index,
    read_datetime_bounds,
)

_executor: Optional[ThreadPoolExecutor] = None


@dataclass
class _PrefetchState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    in_progress: bool = False
    current_keys: tuple[str, ...] | None = None
    progress: dict[str, Any] = field(
        default_factory=lambda: {
            "phase": "idle",
            "detail": "Ready.",
            "files": 0,
            "filters_ready": False,
            "plot_ready": False,
        }
    )

    def default_progress(self) -> dict[str, Any]:
        return {
            "phase": "idle",
            "detail": "Ready.",
            "files": 0,
            "filters_ready": False,
            "plot_ready": False,
        }

    def set_progress(self, **kwargs: Any) -> None:
        with self.lock:
            self.progress = {**self.progress, **kwargs}

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return deepcopy(self.progress)

    def reset(self) -> None:
        with self.lock:
            self.in_progress = False
            self.current_keys = None
            self.progress = self.default_progress()


_STATE = _PrefetchState()


def get_load_progress() -> dict[str, Any]:
    return _STATE.snapshot()


def _ensure_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2)
    return _executor


def start_prefetch(
    selected_keys: list[str],
    *,
    warm_plot_cache: bool = True,
    unit_detail_mode: bool = False,
) -> None:
    """Warm caches in stages: filters first, plot data in background."""
    if not selected_keys:
        _STATE.reset()
        return

    key_tuple = tuple(sorted(selected_keys))
    with _STATE.lock:
        if _STATE.in_progress:
            return
        if _STATE.current_keys == key_tuple and _STATE.progress.get("plot_ready"):
            return
        _STATE.in_progress = True
        _STATE.current_keys = key_tuple
        _STATE.progress = {
            **_STATE.default_progress(),
            "phase": "loading",
            "detail": "Preparing data...",
            "files": len(selected_keys),
        }

    def _task(sig: tuple[tuple[str, str, int], ...], keys: list[str]) -> None:
        try:
            _STATE.set_progress(
                phase="loading",
                detail="Building filter index...",
                files=len(keys),
                filters_ready=False,
                plot_ready=False,
            )
            load_trace_selector_index(keys)
            get_selector_hierarchy(keys)
            read_datetime_bounds(keys, "Datetime")

            _STATE.set_progress(
                phase="filters_ready",
                detail="Trace builder ready. Warming plot cache in background...",
                filters_ready=True,
                plot_ready=False,
            )

            if warm_plot_cache:
                _STATE.set_progress(detail="Preparing plot data...")
                if unit_detail_mode:
                    _load_selected_tables_projected_cached(sig, PLOT_DEFAULT_COLUMNS)
                    _load_selected_tables_cached(sig)
                else:
                    _load_selected_tables_projected_cached(sig, PLOT_DEFAULT_COLUMNS)
                    _load_selected_tables_pemmdb_type_aggregated_cached(sig)

            _STATE.set_progress(
                phase="ready",
                detail="Dashboard ready.",
                filters_ready=True,
                plot_ready=True,
            )
        except Exception:
            _STATE.set_progress(
                phase="error",
                detail="Background loading failed. Data will load on demand.",
                filters_ready=False,
                plot_ready=False,
            )
        finally:
            with _STATE.lock:
                _STATE.in_progress = False

    try:
        sig = _build_selection_signature(selected_keys)
    except Exception:
        _STATE.reset()
        return

    _ensure_executor().submit(_task, sig, selected_keys)


def is_prefetch_in_progress() -> bool:
    with _STATE.lock:
        return _STATE.in_progress
