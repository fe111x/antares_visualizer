from __future__ import annotations

import argparse
import os
import sys
from time import perf_counter

sys.path.insert(0, ".")


def _pick_trace(selector_output: tuple) -> dict | None:
    (
        scenario_options,
        scenario_value,
        market_options,
        market_value,
        ws_options,
        ws_value,
        property_options,
        property_value,
        technology_options,
        technology_value,
    ) = selector_output

    if scenario_value is None or market_value is None or ws_value is None:
        return None

    prop = property_value
    if prop is None and technology_value is not None:
        prop = technology_value
    if prop is None:
        return None

    return {
        "scenario": scenario_value,
        "market_area": market_value,
        "ws": ws_value,
        "property": prop,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark startup to visualizable state")
    parser.add_argument("--blocking-preload", action="store_true", help="Force PRELOAD_BLOCKING=1")
    parser.add_argument("--background-preload", action="store_true", help="Use PRELOAD_BLOCKING=0")
    args = parser.parse_args()

    if args.blocking_preload and args.background_preload:
        parser.error("Use either --blocking-preload or --background-preload, not both.")

    os.environ.setdefault("PRELOAD_ON_START", "1")
    if args.blocking_preload:
        os.environ["PRELOAD_BLOCKING"] = "1"
    elif args.background_preload:
        os.environ["PRELOAD_BLOCKING"] = "0"

    t0 = perf_counter()

    from dashboard.app_factory import create_app
    from dashboard.callbacks import update_controls, update_timeseries, update_trace_selector_options
    from dashboard.data_access import build_file_options, build_run_options

    t_import = perf_counter()

    app = create_app()
    _ = app  # keep local ref for explicitness
    t_app = perf_counter()

    runs = [opt["value"] for opt in build_run_options()]
    files = [opt["value"] for opt in build_file_options(runs)]
    t_discovery = perf_counter()

    (
        _time_opts,
        time_val,
        _value_opts,
        value_val,
        _status,
        loaded_keys,
        _trace_store,
        _fig,
        _note,
        _loaded_dropdown_options,
        _loaded_dropdown_values,
    ) = update_controls(1, files, None, None)
    t_controls = perf_counter()

    selector_output = update_trace_selector_options(1, loaded_keys, None, None, None, None, None)
    trace = _pick_trace(selector_output)
    t_selector = perf_counter()

    first_plot_ok = False
    first_plot_points = 0
    if trace is not None and time_val and value_val:
        figure, _notes = update_timeseries(
            1,
            "line",
            loaded_keys,
            time_val,
            value_val,
            None,
            None,
            "sum",
            [trace],
            {"pemmdb_type_active": False},
        )
        first_plot_ok = bool(getattr(figure, "data", None))
        if first_plot_ok:
            try:
                first_plot_points = len(figure.data[0]["x"])
            except Exception:
                first_plot_points = 0
    t_plot = perf_counter()

    print("=== Benchmark: Start -> Visualizable ===")
    print(f"imports:                    {t_import - t0:8.3f} s")
    print(f"create_app (incl preload):  {t_app - t_import:8.3f} s")
    print(f"discover runs/files:        {t_discovery - t_app:8.3f} s")
    print(f"update_controls:            {t_controls - t_discovery:8.3f} s")
    print(f"trace selector ready:       {t_selector - t_controls:8.3f} s")
    print(f"first visualize call:       {t_plot - t_selector:8.3f} s")
    print(f"TOTAL to visualizable:      {t_selector - t0:8.3f} s")
    print(f"TOTAL incl first plot:      {t_plot - t0:8.3f} s")
    print(f"files loaded:               {len(loaded_keys)}")
    print(f"first plot ok:              {first_plot_ok}")
    print(f"first plot points:          {first_plot_points}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
