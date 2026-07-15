"""
analyze_sine_run.py

Batch analysis script for the sine-wave synchronization test.
Prompts for a folder of Force (Zaber/Futek) run xlsx files and a folder of
CAP/ACC (jlink) run xlsx files, then for every file in each folder:

  - Plots and saves Force vs Time (actual + target/reference if present)
    or CAP vs Time (8 subplots, one per channel)
  - Extracts per-cycle peak-to-peak PERIOD (via scipy.find_peaks) for each
    relevant column, compares the mean achieved frequency (1/period) against
    an expected frequency you provide, and records the result

All frequency-match results (one row per file/column) are written to
frequency_summary.csv.

Additionally, for run-to-run CONSISTENCY checking:
  - Extracts per-cycle peak-to-peak AMPLITUDE and per-cycle PERIOD from each
    run (via scipy.find_peaks), for Force and each CAP channel
  - Runs Welch's ANOVA (unequal-variance safe) + eta-squared effect size
    across runs, separately for amplitude and for period, per signal
  - Writes results to anova_summary.csv

Run directly:
    python analyze_sine_run.py

Requires: pandas, numpy, matplotlib, openpyxl, scipy, pingouin
"""
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from scipy.signal import detrend as scipy_detrend
import pingouin as pg


def find_column(columns, *keywords):
    """Return the first column whose name contains all given keywords (case-insensitive)."""
    for col in columns:
        lowered = col.lower()
        if all(k.lower() in lowered for k in keywords):
            return col
    return None


def list_xlsx_files(folder: Path):
    """Sorted list of .xlsx files in a folder, skipping Excel lock files (~$...)."""
    return sorted(
        f for f in folder.glob("*.xlsx")
        if not f.name.startswith("~$")
    )


def resample_uniform(t: np.ndarray, y: np.ndarray, fs: float = None):
    """Linearly interpolate an irregularly-sampled series onto a uniform time
    grid. If fs isn't given, uses the median sample spacing of t."""
    order = np.argsort(t)
    t = t[order]
    y = y[order]
    if fs is None:
        dt = np.median(np.diff(t))
        fs = 1.0 / dt if dt > 0 else 1.0
    t_uniform = np.arange(t[0], t[-1], 1.0 / fs)
    y_uniform = np.interp(t_uniform, t, y)
    return t_uniform, y_uniform, fs


def extract_cycle_metrics(t: np.ndarray, y: np.ndarray, expected_freq_hz: float, fs: float = None):
    """Resamples/detrends, then finds each cycle's peak and trough to get
    one PERIOD value (time between consecutive peaks) and one AMPLITUDE
    value (peak minus preceding trough) per cycle.

    A minimum peak spacing of half the expected period is enforced so noisy
    wiggles within a single real cycle don't get counted as extra cycles.
    Returns (periods, amplitudes) as numpy arrays.
    """
    t_u, y_u, fs = resample_uniform(t, y, fs=fs)
    y_detrend = scipy_detrend(y_u, type="linear")

    expected_period_s = 1.0 / expected_freq_hz
    min_distance = max(1, int(0.5 * expected_period_s * fs))

    peak_idx, _ = find_peaks(y_detrend, distance=min_distance)
    trough_idx, _ = find_peaks(-y_detrend, distance=min_distance)

    periods = np.diff(t_u[peak_idx]) if len(peak_idx) > 1 else np.array([])

    amplitudes = []
    for p in peak_idx:
        earlier_troughs = trough_idx[trough_idx < p]
        if len(earlier_troughs) == 0:
            continue
        tr = earlier_troughs[-1]
        amplitudes.append(y_detrend[p] - y_detrend[tr])
    amplitudes = np.array(amplitudes)

    return periods, amplitudes


def build_frequency_row(file_name: str, label: str, periods: np.ndarray, expected_freq_hz: float,
                         tol_fraction: float = 0.10, tol_floor_hz: float = 0.02):
    """Builds one CSV row dict comparing achieved frequency (from peak-to-peak
    periods) against the expected/target frequency. tol scales with the
    expected frequency (10% by default) instead of a fixed Hz value."""
    tol_hz = max(tol_floor_hz, tol_fraction * expected_freq_hz)

    if len(periods) == 0:
        return {
            "file": file_name, "column": label,
            "expected_freq_hz": expected_freq_hz,
            "n_cycles": 0,
            "achieved_freq_hz_mean": None,
            "achieved_freq_hz_std": None,
            "tolerance_hz": round(tol_hz, 5),
            "match": None,
            "note": "no peaks found - not enough cycles or signal too noisy",
        }

    achieved_freqs = 1.0 / periods
    mean_freq = float(achieved_freqs.mean())
    std_freq = float(achieved_freqs.std())
    hit = abs(mean_freq - expected_freq_hz) <= tol_hz

    return {
        "file": file_name, "column": label,
        "expected_freq_hz": expected_freq_hz,
        "n_cycles": len(periods),
        "achieved_freq_hz_mean": round(mean_freq, 5),
        "achieved_freq_hz_std": round(std_freq, 5),
        "tolerance_hz": round(tol_hz, 5),
        "match": hit,
        "note": "",
    }


def sampling_summary(file_name: str, t: np.ndarray, expected_freq_hz: float):
    """Measures the actual achieved sample rate from raw (non-resampled)
    timestamps, and derives how many real samples land within one cycle at
    the given test frequency. This is independent of extract_cycle_metrics'
    interpolated grid - it reflects what was really captured, not an
    idealized resample."""
    t_sorted = np.sort(t)
    dt = np.diff(t_sorted)
    dt = dt[dt > 0]  # guard against duplicate/zero-gap timestamps

    if len(dt) == 0:
        return {
            "file": file_name, "n_samples": len(t), "duration_s": 0.0,
            "median_dt_s": None, "effective_fs_hz": None,
            "expected_freq_hz": expected_freq_hz, "samples_per_cycle": None,
        }

    median_dt = float(np.median(dt))
    effective_fs = 1.0 / median_dt if median_dt > 0 else float("nan")
    duration = float(t_sorted[-1] - t_sorted[0])
    samples_per_cycle = effective_fs / expected_freq_hz if expected_freq_hz > 0 else float("nan")

    return {
        "file": file_name,
        "n_samples": len(t),
        "duration_s": round(duration, 3),
        "median_dt_s": round(median_dt, 5),
        "effective_fs_hz": round(effective_fs, 3),
        "expected_freq_hz": expected_freq_hz,
        "samples_per_cycle": round(samples_per_cycle, 2),
    }


def plot_force(force_path: Path, out_dir: Path, expected_freq_hz: float, cycle_records: dict, sampling_rows: list):
    df = pd.read_excel(force_path)

    raw_time_col = find_column(df.columns, "time")
    since_start_col = find_column(df.columns, "since", "start")
    actual_col = find_column(df.columns, "load cell") or find_column(df.columns, "force")
    target_col = find_column(df.columns, "target")

    if raw_time_col is None or actual_col is None:
        print(f"  Could not find Time/Force columns in {force_path.name}: {list(df.columns)}")
        return []

    plot_time_col = since_start_col if since_start_col is not None else raw_time_col

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(df[plot_time_col], df[actual_col], label=actual_col, linewidth=0.9)
    if target_col is not None:
        ax.plot(df[plot_time_col], df[target_col], label=target_col, alpha=0.7, linewidth=0.9)
    ax.set_xlabel(f"{plot_time_col}")
    ax.set_ylabel("Force (N)")
    ax.set_title(f"Force vs Time — {force_path.name}")
    ax.legend()
    fig.tight_layout()

    out_path = out_dir / f"{force_path.stem}_force_vs_time.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")

    freq_rows = []
    t = df[plot_time_col].to_numpy(dtype=float)
    sampling_rows.append(sampling_summary(force_path.name, t, expected_freq_hz))

    columns_to_check = [actual_col] + ([target_col] if target_col is not None else [])
    for col in columns_to_check:
        y = df[col].to_numpy(dtype=float)
        periods, amplitudes = extract_cycle_metrics(t, y, expected_freq_hz)
        freq_rows.append(build_frequency_row(force_path.name, col, periods, expected_freq_hz))

        for p in periods:
            cycle_records["period"][col].append({"run": force_path.name, "value": p})
        for a in amplitudes:
            cycle_records["amplitude"][col].append({"run": force_path.name, "value": a})

    return freq_rows


def plot_caps(cap_path: Path, out_dir: Path, expected_freq_hz: float, cycle_records: dict, sampling_rows: list):
    df = pd.read_excel(cap_path)

    time_col = find_column(df.columns, "time")
    if time_col is None:
        print(f"  Could not find a Time column in {cap_path.name}: {list(df.columns)}")
        return []

    cap_cols = [c for c in df.columns if c.upper().startswith("CAP")]
    cap_cols = sorted(cap_cols, key=lambda c: c.upper())[:8]

    if not cap_cols:
        print(f"  No CAP columns found in {cap_path.name}: {list(df.columns)}")
        return []

    fig, axes = plt.subplots(4, 2, figsize=(12, 12), sharex=True)
    axes = axes.flatten()

    for i, ax in enumerate(axes):
        if i < len(cap_cols):
            col = cap_cols[i]
            ax.plot(df[time_col], df[col], linewidth=0.8, color=f"C{i}")
            ax.set_title(col, fontsize=10)
            ax.set_ylabel("pF", fontsize=8)
        else:
            ax.axis("off")
        if i >= 6:
            ax.set_xlabel(time_col)

    fig.suptitle(f"CAP channels vs Time — {cap_path.name}")
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    out_path = out_dir / f"{cap_path.stem}_cap_vs_time.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")

    freq_rows = []
    t = df[time_col].to_numpy(dtype=float)
    sampling_rows.append(sampling_summary(cap_path.name, t, expected_freq_hz))

    for col in cap_cols:
        y = df[col].to_numpy(dtype=float)
        periods, amplitudes = extract_cycle_metrics(t, y, expected_freq_hz)
        freq_rows.append(build_frequency_row(cap_path.name, col, periods, expected_freq_hz))

        for p in periods:
            cycle_records["period"][col].append({"run": cap_path.name, "value": p})
        for a in amplitudes:
            cycle_records["amplitude"][col].append({"run": cap_path.name, "value": a})

    return freq_rows


def run_welch_anova(cycle_records: dict, metric: str):
    """For each signal (column) under cycle_records[metric], builds a long
    DataFrame of {run, value} across all runs and computes Welch's ANOVA +
    eta-squared, grouping by run. Returns a list of result-row dicts.

    Welch's ANOVA weights each group by n/variance; a group with zero (or
    NaN) variance makes that weight infinite, which produces a NaN grand
    mean (inf/inf) inside pingouin and throws a RuntimeWarning. This is
    checked for up front and that signal is skipped with an explanatory
    note instead of passing bad data into pingouin.
    """
    rows = []
    for signal, records in cycle_records[metric].items():
        df = pd.DataFrame(records)
        n_runs = df["run"].nunique()
        if n_runs < 2 or len(df) < n_runs * 2:
            rows.append({
                "signal": signal, "metric": metric, "n_runs": n_runs,
                "n_observations": len(df), "F": None, "p_unc": None,
                "eta_squared": None, "note": "insufficient data for ANOVA",
            })
            continue

        group_stats = df.groupby("run")["value"].agg(["count", "var"])
        bad_groups = group_stats[
            (group_stats["count"] < 2) | group_stats["var"].isna() | (group_stats["var"] <= 0)
        ]
        if not bad_groups.empty:
            rows.append({
                "signal": signal, "metric": metric, "n_runs": n_runs,
                "n_observations": len(df), "F": None, "p_unc": None,
                "eta_squared": None,
                "note": (f"zero/undefined variance in run(s) "
                         f"{list(bad_groups.index)} - likely a deterministic "
                         f"reference signal or a flat/dead channel; Welch's "
                         f"ANOVA skipped"),
            })
            continue

        try:
            result = pg.welch_anova(data=df, dv="value", between="run")
            r = result.iloc[0]
            # pingouin has used both "p-unc" (older) and "p_unc" (newer) column names
            p_col = "p-unc" if "p-unc" in result.columns else "p_unc"
            rows.append({
                "signal": signal, "metric": metric, "n_runs": n_runs,
                "n_observations": len(df),
                "F": round(float(r["F"]), 4),
                "p_unc": round(float(r[p_col]), 6),
                "eta_squared": round(float(r["np2"]), 4),
                "note": "",
            })
        except Exception as exc:
            rows.append({
                "signal": signal, "metric": metric, "n_runs": n_runs,
                "n_observations": len(df), "F": None, "p_unc": None,
                "eta_squared": None, "note": f"ANOVA failed: {exc}",
            })
    return rows


def prompt_folder(prompt_text):
    raw = input(prompt_text).strip().strip('"').strip("'")
    if not raw:
        return None
    folder = Path(raw)
    if not folder.is_dir():
        print(f"  Not a folder: {folder}")
        return None
    return folder


def main():
    print("Sine test analysis (folder mode, peak-to-peak frequency + run-to-run ANOVA) — press Enter to skip a folder.\n")

    force_folder = prompt_folder("Folder of Force/Load-cell xlsx files: ")
    cap_folder = prompt_folder("Folder of CAP/jlink xlsx files: ")

    freq_input = input("Expected sine frequency in Hz [default 0.5]: ").strip()
    expected_freq_hz = float(freq_input) if freq_input else 0.5

    out_dir = Path("./sine_analysis_output_0.25hz")
    out_dir.mkdir(exist_ok=True)

    freq_rows = []
    sampling_rows = []
    # cycle_records["period"|"amplitude"][signal_name] = list of {"run":..., "value":...}
    cycle_records = {"period": defaultdict(list), "amplitude": defaultdict(list)}

    if force_folder is not None:
        force_files = list_xlsx_files(force_folder)
        if not force_files:
            print(f"  No xlsx files found in {force_folder}")
        for f in force_files:
            print(f"Processing {f.name}...")
            freq_rows.extend(plot_force(f, out_dir, expected_freq_hz, cycle_records, sampling_rows))

    if cap_folder is not None:
        cap_files = list_xlsx_files(cap_folder)
        if not cap_files:
            print(f"  No xlsx files found in {cap_folder}")
        for f in cap_files:
            print(f"Processing {f.name}...")
            freq_rows.extend(plot_caps(f, out_dir, expected_freq_hz, cycle_records, sampling_rows))

    if sampling_rows:
        sampling_path = out_dir / "sampling_summary.csv"
        pd.DataFrame(sampling_rows).to_csv(sampling_path, index=False)
        print(f"Sampling rate summary saved to: {sampling_path.resolve()}")

    if freq_rows:
        freq_summary_path = out_dir / "frequency_summary.csv"
        pd.DataFrame(freq_rows).to_csv(freq_summary_path, index=False)
        print(f"\nFrequency summary saved to: {freq_summary_path.resolve()}")
    else:
        print("\nNo frequency results to save.")

    anova_rows = run_welch_anova(cycle_records, "amplitude") + run_welch_anova(cycle_records, "period")

    # Holm-Bonferroni correction across the full family of tests (both metrics
    # together, since that's the complete set of comparisons actually run).
    # Rows with no p-value (insufficient data / zero-variance skip) are left blank.
    valid_idx = [i for i, r in enumerate(anova_rows) if r["p_unc"] is not None]
    if valid_idx:
        pvals = [anova_rows[i]["p_unc"] for i in valid_idx]
        reject, pvals_holm = pg.multicomp(pvals, alpha=0.05, method="holm")
        for idx, p_holm, sig in zip(valid_idx, pvals_holm, reject):
            anova_rows[idx]["p_holm"] = round(float(p_holm), 6)
            anova_rows[idx]["significant_holm"] = bool(sig)
    for r in anova_rows:
        r.setdefault("p_holm", None)
        r.setdefault("significant_holm", None)

    if anova_rows:
        anova_path = out_dir / "anova_summary.csv"
        pd.DataFrame(anova_rows).to_csv(anova_path, index=False)
        print(f"Run-to-run ANOVA (amplitude + period) saved to: {anova_path.resolve()}")
    else:
        print("No cycle data available for ANOVA.")

    print(f"Plots saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()