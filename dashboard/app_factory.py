from __future__ import annotations

from dash import Dash
import logging
import os
from time import perf_counter

from .callbacks import register_callbacks
from .config import BASE_DIR
from .data_access import build_file_options, build_run_options
from .layout import build_layout


def create_app() -> Dash:
    # Configure application-wide logging. Honor LOG_LEVEL env var (DEBUG/INFO/WARNING/ERROR).
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # Reduce noise from some noisy libraries by default.
    for lib in ("urllib3", "botocore", "matplotlib", "asyncio"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    app = Dash(__name__, assets_folder=str(BASE_DIR / "assets"))
    app.title = "Antares Output Visualizer"

    initial_run_options = build_run_options()
    initial_run_value = [option["value"] for option in initial_run_options]
    initial_file_options = build_file_options(initial_run_value) if initial_run_value else []
    initial_file_values = [option["value"] for option in initial_file_options]

    app.layout = build_layout(
        initial_run_options,
        initial_run_value,
        initial_file_options,
        initial_file_values,
    )

    # Initialize persistent cache (Redis if configured, otherwise filesystem cache)
    try:
        from flask_caching import Cache
        # 'os' is imported at module level; do not re-import here to avoid
        # creating a local variable that shadows the module-level name.

        cache_config = {
            "CACHE_TYPE": "FileSystemCache",
            "CACHE_DIR": str(BASE_DIR / ".cache"),
            "CACHE_DEFAULT_TIMEOUT": 3600,
        }
        redis_url = os.environ.get("REDIS_URL") or os.environ.get("CACHE_REDIS_URL")
        if redis_url:
            cache_config = {
                "CACHE_TYPE": "RedisCache",
                "CACHE_REDIS_URL": redis_url,
                "CACHE_DEFAULT_TIMEOUT": 0,
            }

        cache = Cache()
        cache.init_app(app.server, config=cache_config)
        # Expose cache to data_access for use in persistent caching
        try:
            from . import data_access

            data_access.CACHE = cache
        except Exception:
            pass
    except Exception:
        # Flask-Caching not available; continue without persistent cache
        pass

    register_callbacks(app)
    # Ensure Flask/Dash server logger uses the configured handlers/level.
    app.server.logger.setLevel(numeric_level)
    root_handlers = logging.getLogger().handlers
    if root_handlers:
        for h in root_handlers:
            if h not in app.server.logger.handlers:
                app.server.logger.addHandler(h)
    logging.getLogger(__name__).info("App initialized with log level %s", log_level)
    # Optionally warm caches on startup to make first UI interactions fast.
    try:
        preload = os.environ.get("PRELOAD_ON_START", "0") in ("1", "true", "True")
        blocking = os.environ.get("PRELOAD_BLOCKING", "0") in ("1", "true", "True")
        preload_full_tables = os.environ.get("PRELOAD_FULL_TABLES", "0") in ("1", "true", "True")
        if preload:
            t0 = perf_counter()
            logging.getLogger(__name__).info(
                "Preloading selected files into cache (blocking=%s, full_tables=%s)",
                blocking,
                preload_full_tables,
            )
            try:
                from . import data_access
                from .prefetch import start_prefetch

                file_keys = initial_file_values or [opt["value"] for opt in build_file_options(None)]
                if blocking:
                    try:
                        data_access.load_trace_selector_index(file_keys)
                        data_access.get_selector_hierarchy(file_keys)
                        if preload_full_tables:
                            data_access.load_selected_tables(file_keys)
                        elapsed = perf_counter() - t0
                        logging.getLogger(__name__).info(
                            "Startup preload finished for %d files in %.2fs",
                            len(file_keys),
                            elapsed,
                        )
                    except Exception:
                        logging.getLogger(__name__).exception("Blocking preload failed, falling back to background prefetch")
                        start_prefetch(file_keys, warm_plot_cache=True)
                else:
                    start_prefetch(file_keys, warm_plot_cache=True)
                    elapsed = perf_counter() - t0
                    logging.getLogger(__name__).info(
                        "Startup background preload scheduled for %d files in %.2fs",
                        len(file_keys),
                        elapsed,
                    )
            except Exception:
                logging.getLogger(__name__).exception("Failed to start preload task")
    except Exception:
        pass
    return app
