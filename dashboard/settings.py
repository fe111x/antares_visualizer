from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import BASE_DIR, DATA_DIR

DEFAULT_CONFIG_PATH = BASE_DIR / "visualizer_config.yaml"
CONFIG_ENV_VAR = "VISUALIZER_CONFIG"


@dataclass(frozen=True)
class AppSettings:
    """Path layout: runs_root / <run_id> / run_data_path / *.parquet"""

    runs_root: Path
    run_data_path: Path | None = None


def _resolve_path(value: str | Path, *, base: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _default_settings() -> AppSettings:
    return AppSettings(runs_root=DATA_DIR.resolve())


def _parse_run_data_path(raw: Any) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    segment = raw.strip()
    if segment in (".", "./"):
        return None
    return Path(segment)


def load_settings(config_path: Path | None = None) -> AppSettings:
    path = config_path or Path(__import__("os").environ.get(CONFIG_ENV_VAR, str(DEFAULT_CONFIG_PATH)))
    if not path.exists():
        return _default_settings()

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except Exception:
        return _default_settings()

    if not isinstance(raw, dict):
        return _default_settings()

    runs_root_raw = raw.get("runs_root", "data")
    runs_root = _resolve_path(str(runs_root_raw), base=BASE_DIR)

    # Single subfolder inside every run directory (not per-run entries in YAML).
    run_data_path = _parse_run_data_path(raw.get("run_data_path"))
    if run_data_path is None:
        run_data_path = _parse_run_data_path(raw.get("data_path"))

    return AppSettings(runs_root=runs_root, run_data_path=run_data_path)


def reload_settings() -> AppSettings:
    get_settings.cache_clear()
    return get_settings()


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return load_settings()


def get_runs_root() -> Path:
    return get_settings().runs_root


def list_run_ids() -> list[str]:
    """Discover run folders directly under runs_root (no YAML run list)."""
    runs_root = get_settings().runs_root
    if not runs_root.is_dir():
        return []
    return sorted(
        child.name
        for child in runs_root.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    )


def get_run_data_dir(run_id: str) -> Path:
    settings = get_settings()
    run_root = (settings.runs_root / run_id).resolve()
    if settings.run_data_path is None:
        return run_root
    return _resolve_path(settings.run_data_path, base=run_root)


def run_key_prefix(run_id: str) -> str:
    settings = get_settings()
    try:
        return (settings.runs_root / run_id).resolve().relative_to(BASE_DIR).as_posix()
    except ValueError:
        return f"@{run_id}"


def invalidate_path_caches() -> None:
    reload_settings()
    try:
        from .data_access import discover_input_files

        discover_input_files.cache_clear()
    except Exception:
        pass
