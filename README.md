# Antares Visualizer

Interactive Dash dashboard for exploring Antares model output files (`.parquet` / `.csv`) as time series, stacked areas, duration curves, and density plots.

## Features

- Multiple runs under `data/` (one folder per run)
- Trace builder: Run → weather scenario → market area → property (with optional PEMMDB technology)
- Per-trace aggregation and time buckets (hourly / daily / weekly / monthly) as step plots
- PEMMDB technology-level aggregation by default, optional unit-level detail
- Cached loading for faster interaction on large datasets

## Project layout

```text
antares_visualizer/
  dashboard_app.py          # Entry point
  start_service.ps1         # Windows production start (Waitress)
  visualizer_config.yaml    # runs_root and per-run data_path
  dashboard/                # App code
  assets/                   # CSS
  data/                     # Your Antares outputs (not in git)
  scripts/                  # Deployment and utilities
  requirements.txt
```

## Data setup

Place Antares output files under `data/`, one subdirectory per run:

```text
data/
  run_AT/
    *.parquet
  run_DE/
    output/hourly/
      *.parquet
```

Every folder under `data/` is discovered automatically. Optional overrides go in `visualizer_config.yaml`:

```yaml
runs_root: data
runs:
  run_DE:
    data_path: output/hourly
```

Set a custom config path:

```powershell
$env:VISUALIZER_CONFIG = "C:\path\to\visualizer_config.yaml"
```

## Local development

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python dashboard_app.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
POLARS_SKIP_CPU_CHECK=1 python dashboard_app.py
```

Open http://127.0.0.1:8050/

### Optional environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `127.0.0.1` | Bind address (`dashboard_app.py` dev server) |
| `PORT` | `8050` | Listen port |
| `VISUALIZER_CONFIG` | `./visualizer_config.yaml` | Path to YAML config |
| `POLARS_SKIP_CPU_CHECK` | unset | Set to `1` on older CPUs if Polars warns |
| `PRELOAD_ON_START` | `0` | Warm caches at startup |
| `PRELOAD_BLOCKING` | `0` | Block until preload finishes |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Usage

1. All runs under `data/` are pre-selected in the **Runs** dropdown.
2. Click **Load Data**.
3. Build traces in the trace builder (Run → WS → market area → property / technology).
4. Click **Visualize**.

Use **Refresh file list** after adding new run folders or files.

## Windows server deployment

The app runs as a **Scheduled Task** at startup (no Docker required). The install script creates the venv, installs dependencies, and starts **Waitress** via `start_service.ps1` using the venv Python directly — no manual `Activate.ps1` in the service.

### 1. Install (Administrator PowerShell)

From the project root:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
.\scripts\install_windows_service.ps1
```

With a corporate proxy **for pip only** (during dependency install):

```powershell
.\scripts\install_windows_service.ps1 -ProxyUrl "http://USER:PASSWORD@proxy.example.com:8080"
```

Other parameters:

```powershell
.\scripts\install_windows_service.ps1 -Port 8050 -BindHost "0.0.0.0" -TaskName "AntaresOutputVisualizer"
```

### 2. Verify

```powershell
Get-ScheduledTask -TaskName AntaresOutputVisualizer
Get-ScheduledTaskInfo -TaskName AntaresOutputVisualizer
```

Dashboard URL: `http://<server-ip>:8050/`

### 3. Logs

- `logs/service.log` — start/stop messages from `start_service.ps1`
- `logs/dashboard.out.log` — Waitress stdout
- `logs/dashboard.err.log` — Waitress stderr

### 4. Remove

```powershell
.\scripts\remove_windows_service.ps1
```

### Manual production start (without scheduled task)

```powershell
.\start_service.ps1 -BindHost "0.0.0.0" -Port 8050
```

## Utility scripts

```powershell
python scripts/inspect_parquet.py path\to\file.parquet
python scripts/generate_sample_data.py
python scripts/benchmark_start_to_visualizable.py
```

## License

Internal / project use — adjust as needed for your organisation.
