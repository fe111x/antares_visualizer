"""
Erzeugt Beispieldaten im ERAA-Format (36 Klimajahre × 10 Samples) für Tests der Pipeline.

Führt man dieses Skript aus und danach die Visualisierungspipeline, entstehen
Beispiel-HTML-Plots auch ohne echte Modelloutputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

# Typische ERAA-Study-Zonen (Ausschnitt)
STUDY_ZONES = ["AT00", "BE00", "DE00", "FR00", "NL00", "PL00", "CZ00", "ITN1", "ES00", "UK00"]
TARGET_YEARS = [2025, 2028, 2030, 2033]
N_CLIMATE_YEARS = 36
N_SAMPLES = 10
TECHNOLOGIES = [
    "Nuclear", "Lignite", "Hard Coal", "Gas CCGT", "Gas OCGT", "Wind Onshore",
    "Wind Offshore", "Solar", "Hydro Run-of-River", "Hydro Pumped Storage",
]


def generate_adequacy(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for zone in STUDY_ZONES:
        for ty in TARGET_YEARS:
            base_lole = rng.uniform(0.1, 3.0)
            base_ens = rng.uniform(0.01, 2.0)
            for cy in range(1, N_CLIMATE_YEARS + 1):
                for sid in range(1, N_SAMPLES + 1):
                    rows.append({
                        "study_zone": zone,
                        "target_year": ty,
                        "scenario": "A",
                        "climate_year": cy,
                        "sample_id": sid,
                        "lole": max(0, base_lole + rng.normal(0, 0.5)),
                        "eens": max(0, base_ens + rng.normal(0, 0.3)),
                        "lld": int(rng.integers(0, 10)),
                        "ens": max(0, base_ens * 0.5 + rng.normal(0, 0.2)),
                        "p50_lld": 0,
                        "p95_lld": int(rng.integers(5, 20)),
                        "p50_ens": 0,
                        "p95_ens": max(0, base_ens + rng.uniform(0, 1)),
                    })
    return pd.DataFrame(rows)


def generate_dispatch(rng: np.random.Generator, n_hours: int = 8760) -> pd.DataFrame:
    # Reduziert: 12 Monate × 24 h, aber nur 2 Zeitschritte pro Tag für schnelles Beispiel
    rows = []
    for zone in STUDY_ZONES[:4]:
        for ty in TARGET_YEARS[:2]:
            for tech in TECHNOLOGIES:
                for cy in range(1, 4):
                    for sid in range(1, 3):
                        for month in range(1, 13):
                            for hour in range(0, 24, 2):  # alle 2 h für Stunde×Monat-Heatmap
                                dt = f"2025-{month:02d}-15T{hour:02d}:00:00"
                                rows.append({
                                    "study_zone": zone,
                                    "target_year": ty,
                                    "technology": tech,
                                    "datetime": dt,
                                    "climate_year": cy,
                                    "sample_id": sid,
                                    "generation_mw": max(0, rng.uniform(100, 2000)),
                                    "load_mw": 0 if "Pumped" not in tech else rng.uniform(0, 200),
                                })
    return pd.DataFrame(rows)


def generate_adequacy_hour_month(rng: np.random.Generator) -> pd.DataFrame:
    """Adequacy auf Stunde (0–23) × Monat (1–12) verteilt; typisches Muster: mehr im Winter, mehr in Lastspitzen."""
    month_weight = np.array([1.2, 1.1, 0.9, 0.7, 0.6, 0.6, 0.6, 0.7, 0.8, 0.9, 1.1, 1.3])
    hour_weight = np.ones(24)
    for h in (7, 8, 9, 10, 17, 18, 19, 20):
        hour_weight[h] = 1.5
    profile = np.outer(hour_weight, month_weight)
    profile = profile / profile.sum()

    rows = []
    for zone in STUDY_ZONES:
        for ty in TARGET_YEARS:
            base_lole = rng.uniform(0.5, 2.0)
            base_ens = rng.uniform(0.05, 1.0)
            for cy in range(1, min(5, N_CLIMATE_YEARS + 1)):
                for sid in range(1, min(4, N_SAMPLES + 1)):
                    lole_y = max(0.1, base_lole + rng.normal(0, 0.3))
                    ens_y = max(0.01, base_ens + rng.normal(0, 0.2))
                    for month in range(1, 13):
                        for hour in range(24):
                            w = profile[hour, month - 1]
                            rows.append({
                                "study_zone": zone,
                                "target_year": ty,
                                "climate_year": cy,
                                "sample_id": sid,
                                "month": month,
                                "hour": hour,
                                "lole_h": lole_y * w,
                                "ens_mwh": ens_y * 1000 * w,
                            })
    return pd.DataFrame(rows)


def generate_net_position(rng: np.random.Generator, n_hours: int = 24 * 31) -> pd.DataFrame:
    rows = []
    for zone in STUDY_ZONES[:5]:
        for ty in TARGET_YEARS[:2]:
            for cy in range(1, 3):
                for sid in range(1, 3):
                    for month in range(1, 13):
                        for hour in (0, 8, 12, 18):
                            rows.append({
                                "study_zone": zone,
                                "target_year": ty,
                                "datetime": f"2025-{month:02d}-15T{hour:02d}:00:00",
                                "climate_year": cy,
                                "sample_id": sid,
                                "net_position_mw": rng.uniform(-2000, 2000),
                            })
    return pd.DataFrame(rows)


def generate_prices(rng: np.random.Generator, n_hours: int = 24 * 31) -> pd.DataFrame:
    rows = []
    for zone in STUDY_ZONES[:5]:
        for ty in TARGET_YEARS[:2]:
            for cy in range(1, 3):
                for sid in range(1, 3):
                    for month in range(1, 13):
                        for hour in (0, 8, 12, 18):
                            rows.append({
                                "study_zone": zone,
                                "target_year": ty,
                                "datetime": f"2025-{month:02d}-15T{hour:02d}:00:00",
                                "climate_year": cy,
                                "sample_id": sid,
                                "price_eur_mwh": max(0, rng.uniform(20, 120)),
                            })
    return pd.DataFrame(rows)


def generate_storage(rng: np.random.Generator, n_hours: int = 24 * 31) -> pd.DataFrame:
    rows = []
    for zone in ["DE00", "AT00", "FR00"]:
        for ty in TARGET_YEARS[:2]:
            for stype in ["Battery", "Hydro Pumped Storage"]:
                for cy in range(1, 3):
                    for sid in range(1, 3):
                        level = 50.0
                        for t in range(0, n_hours, 4):
                            level = np.clip(level + rng.normal(0, 5), 0, 100)
                            rows.append({
                                "study_zone": zone,
                                "target_year": ty,
                                "storage_type": stype,
                                "datetime": f"2025-01-01T{t:02d}:00:00",
                                "climate_year": cy,
                                "sample_id": sid,
                                "level_pct": float(level),
                                "level_mwh": level * 100,
                            })
    return pd.DataFrame(rows)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "data"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    generate_adequacy(rng).to_csv(out / "adequacy.csv", index=False)
    generate_adequacy_hour_month(rng).to_csv(out / "adequacy_hour_month.csv", index=False)
    generate_dispatch(rng).to_csv(out / "dispatch.csv", index=False)
    generate_net_position(rng).to_csv(out / "net_position.csv", index=False)
    generate_prices(rng).to_csv(out / "prices.csv", index=False)
    generate_storage(rng).to_csv(out / "storage.csv", index=False)
    print("Sample data written to", out)


if __name__ == "__main__":
    main()
