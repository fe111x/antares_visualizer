from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import BASE_DIR, DATA_DIR

DEFAULT_CONFIG_PATH = BASE_DIR / "visualizer_config.yaml"
CONFIG_ENV_VAR = "VISUALIZER_CONFIG"


@dataclass(frozen=True)
class RunSettings:
    data_path: str | None = None


@dataclass(frozen=True)
class AppSettings:
    runs_root: Path
    runs: dict[str, RunSettings] = field(default_factory=dict)


def _resolve_path(value: str | Path, *, base: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _default_settings() -> AppSettings:
    return AppSettings(runs_root=DATA_DIR.resolve())


def _parse_run_settings(raw_runs: Any) -> dict[str, RunSettings]:
    if not isinstance(raw_runs, dict):
        return {}
    parsed: dict[str, RunSettings] = {}
    for run_id, config in raw_runs.items():
        if not isinstance(run_id, str) or not run_id.strip():
            continue
        data_path = None
        if isinstance(config, dict):
            value = config.get("data_path")
            if isinstance(value, str) and value.strip():
                data_path = value.strip()
        elif isinstance(config, str) and config.strip():
            data_path = config.strip()
        parsed[run_id.strip()] = RunSettings(data_path=data_path)
    return parsed


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
    runs = _parse_run_settings(raw.get("runs"))
    return AppSettings(runs_root=runs_root, runs=runs)


def reload_settings() -> AppSettings:
    get_settings.cache_clear()
    return get_settings()


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return load_settings()


def get_runs_root() -> Path:
    return get_settings().runs_root


def list_run_ids() -> list[str]:
    settings = get_settings()
    runs_root = settings.runs_root
    configured = set(settings.runs.keys())
    discovered: set[str] = set()
    if runs_root.is_dir():
        for child in runs_root.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                discovered.add(child.name)
    return sorted(configured | discovered)


def get_run_data_dir(run_id: str) -> Path:
    settings = get_settings()
    run_root = settings.runs_root / run_id
    run_settings = settings.runs.get(run_id)
    if run_settings and run_settings.data_path:
        return _resolve_path(run_settings.data_path, base=run_root)
    return run_root.resolve()


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
