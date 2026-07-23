"""
analyze_triangle_run.py

Batch analysis script for the triangle-wave (bang-bang) synchronization test.
Prompts for a folder of Force (Zaber/Futek) run xlsx files and a folder of
CAP/ACC (jlink) run xlsx files, then for every file in each folder:

  - Plots and saves Force vs Time (with a Position vs Time subplot underneath,
    since the triangle test logs actual Zaber readback per sample) or
    CAP vs Time (8 subplots, one per channel), with:
      * the raw signal (dimmed when spline is active)
      * an optional spline overlay so you can see what the peak-detector
        is actually acting on
      * detected peaks (▲) and troughs (▼) marked on the spline curve
  - Extracts per-cycle peak-to-peak PERIOD (via scipy.find_peaks) for each
    relevant column, compares the mean achieved frequency (1/period) against
    the run's own target frequency (read from the file's metadata cells, or
    a global default if that can't be parsed), and records the result
  - For Force files, also reads back the metadata your run_triangle_test
    writes (target freq, reversal-derived achieved freq, calibrated depth
    range) and cross-checks the reversal-counting frequency estimate against
    this script's independent peak-detection estimate

All frequency-match results (one row per file/column) are written to
frequency_summary.csv.

Additionally, for run-to-run CONSISTENCY checking:
  - Extracts per-cycle peak-to-peak AMPLITUDE and per-cycle PERIOD from each
    run, for Force and each CAP channel
  - Runs Welch's ANOVA + eta-squared across runs, separately for amplitude
    and for period, per signal
  - Writes results to anova_summary.csv

Run directly:
    python analyze_triangle_run.py

Requires: pandas, numpy, matplotlib, openpyxl, scipy, pingouin
"""
import re
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from scipy.signal import detrend as scipy_detrend
from scipy.interpolate import UnivariateSpline
import pingouin as pg


def find_column(columns, *keywords):
    """Return the first column whose name contains all given keywords (case-insensitive)."""
    for col in columns:
        lowered = str(col).lower()
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
    """Linearly interpolate an irregularly-sampled series onto a uniform time grid."""
    order = np.argsort(t)
    t = t[order]
    y = y[order]
    if fs is None:
        dt = np.median(np.diff(t))
        fs = 1.0 / dt if dt > 0 else 1.0
    t_uniform = np.arange(t[0], t[-1], 1.0 / fs)
    y_uniform = np.interp(t_uniform, t, y)
    return t_uniform, y_uniform, fs


def fit_spline(t_u: np.ndarray, y_u: np.ndarray, s: float) -> np.ndarray:
    """Fit a smoothing spline to a uniformly-sampled signal and return the
    smoothed values evaluated at every point in t_u.

    The spline is fit on the ORIGINAL (non-detrended) signal so the
    returned values stay in the original physical units (N or pF) and
    can be overlaid directly on the raw signal plot without any
    trend-compensation arithmetic.

    Parameters
    ----------
    t_u : uniform time grid from resample_uniform
    y_u : signal values on that grid (original units, not detrended)
    s   : UnivariateSpline smoothing factor.
          Larger s → smoother curve (fewer knots, less faithful to raw data).
          Smaller s → tighter fit (more knots, more noise gets through).
          A practical starting range is 1×–10× len(t_u).
          Check sampling_summary.csv for your signal's sample count, then
          try e.g. 5000, 25000, 100000 and compare the overlaid spline plots.

    Returns
    -------
    y_smooth : np.ndarray, same shape as t_u / y_u
    """
    spline = UnivariateSpline(t_u, y_u, s=s)
    return spline(t_u)


def reject_extrema_outliers(y_detrend: np.ndarray, idx: np.ndarray, mad_thresh: float = 3.5):
    """Given peak or trough indices into y_detrend, flags and removes any
    whose height is an outlier relative to its fellow peaks/troughs, using
    a robust modified z-score (median absolute deviation, not mean/std, so
    the false peaks being screened out don't themselves skew the threshold).

    mad_thresh: modified z-score cutoff. 3.5 is a common default (Iglewicz &
    Hoaglin). Lower = more aggressive rejection, higher = more permissive.

    Returns (kept_idx, n_removed).
    """
    if len(idx) < 3:
        return idx, 0  # not enough points to judge "relative to its fellows"

    vals = y_detrend[idx]
    median = np.median(vals)
    mad = np.median(np.abs(vals - median))

    if mad == 0:
        return idx, 0  # all identical - nothing to flag

    modified_z = 0.6745 * (vals - median) / mad
    keep_mask = np.abs(modified_z) <= mad_thresh

    return idx[keep_mask], int((~keep_mask).sum())


def extract_cycle_metrics(t: np.ndarray, y: np.ndarray, expected_freq_hz: float,
                          fs: float = None, spline_s: float = None,
                          outlier_mad_thresh: float = 6.5):
    t_u, y_u, fs = resample_uniform(t, y, fs=fs)

    if spline_s is not None:
        y_smooth = fit_spline(t_u, y_u, s=spline_s)
    else:
        y_smooth = y_u

    y_detrend = scipy_detrend(y_smooth, type="linear")

    expected_period_s = 1.0 / expected_freq_hz
    # Triangle edges are sharper than sine, but find_peaks is shape-agnostic -
    # this distance floor still just prevents double-counting a single ramp
    # apex as multiple peaks.
    min_distance = max(1, int(0.5 * expected_period_s * fs))

    peak_idx,   _ = find_peaks( y_detrend, distance=min_distance)
    trough_idx, _ = find_peaks(-y_detrend, distance=min_distance)

    peak_idx, n_peaks_removed = reject_extrema_outliers(y_detrend, peak_idx, outlier_mad_thresh)
    trough_idx, n_troughs_removed = reject_extrema_outliers(y_detrend, trough_idx, outlier_mad_thresh)

    if n_peaks_removed or n_troughs_removed:
        print(f"  [outlier filter] removed {n_peaks_removed} peak(s), "
              f"{n_troughs_removed} trough(s) as height outliers")

    periods = np.diff(t_u[peak_idx]) if len(peak_idx) > 1 else np.array([])

    amplitudes = []
    for p in peak_idx:
        earlier_troughs = trough_idx[trough_idx < p]
        if len(earlier_troughs) == 0:
            continue
        tr = earlier_troughs[-1]
        amplitudes.append(y_detrend[p] - y_detrend[tr])
    amplitudes = np.array(amplitudes)

    peak_times   = t_u[peak_idx]   if len(peak_idx)   > 0 else np.array([])
    trough_times = t_u[trough_idx] if len(trough_idx) > 0 else np.array([])

    return periods, amplitudes, peak_times, trough_times, t_u, y_smooth


def build_frequency_row(file_name: str, label: str, periods: np.ndarray,
                         expected_freq_hz: float, tol_fraction: float = 0.10,
                         tol_floor_hz: float = 0.02, extra: dict = None):
    """Builds one CSV row comparing achieved frequency against the target."""
    tol_hz = max(tol_floor_hz, tol_fraction * expected_freq_hz)

    if len(periods) == 0:
        row = {
            "file": file_name, "column": label,
            "expected_freq_hz": expected_freq_hz, "n_cycles": 0,
            "achieved_freq_hz_mean": None, "achieved_freq_hz_std": None,
            "tolerance_hz": round(tol_hz, 5), "match": None,
            "note": "no peaks found - not enough cycles or signal too noisy",
        }
    else:
        achieved_freqs = 1.0 / periods
        mean_freq = float(achieved_freqs.mean())
        std_freq  = float(achieved_freqs.std())
        hit = abs(mean_freq - expected_freq_hz) <= tol_hz

        row = {
            "file": file_name, "column": label,
            "expected_freq_hz": expected_freq_hz,
            "n_cycles": len(periods),
            "achieved_freq_hz_mean": round(mean_freq, 5),
            "achieved_freq_hz_std": round(std_freq, 5),
            "tolerance_hz": round(tol_hz, 5),
            "match": hit, "note": "",
        }

    if extra:
        row.update(extra)
    return row


def sampling_summary(file_name: str, t: np.ndarray, expected_freq_hz: float):
    """Measures the actual achieved sample rate from raw timestamps."""
    t_sorted = np.sort(t)
    dt = np.diff(t_sorted)
    dt = dt[dt > 0]

    if len(dt) == 0:
        return {
            "file": file_name, "n_samples": len(t), "duration_s": 0.0,
            "median_dt_s": None, "effective_fs_hz": None,
            "expected_freq_hz": expected_freq_hz, "samples_per_cycle": None,
        }

    median_dt    = float(np.median(dt))
    effective_fs = 1.0 / median_dt if median_dt > 0 else float("nan")
    duration     = float(t_sorted[-1] - t_sorted[0])
    samples_per_cycle = effective_fs / expected_freq_hz if expected_freq_hz > 0 else float("nan")

    return {
        "file": file_name, "n_samples": len(t),
        "duration_s": round(duration, 3),
        "median_dt_s": round(median_dt, 5),
        "effective_fs_hz": round(effective_fs, 3),
        "expected_freq_hz": expected_freq_hz,
        "samples_per_cycle": round(samples_per_cycle, 2),
    }


def read_triangle_metadata(force_path: Path):
    """Read back the single-cell metadata run_triangle_test writes to H1/I1/J1
    of the Force xlsx: target freq, reversal-derived achieved freq, and the
    calibrated depth range. These are plain strings in a single cell each
    (not per-row columns), so pandas' normal column parsing won't line them
    up with data rows - read them directly off row 0 by position instead.

    Returns a dict with any of target_freq_hz / test_reported_achieved_freq_hz /
    calibrated_depth_range_mm that could be parsed, or an empty dict if the
    file doesn't have this triangle-test metadata layout.
    """
    try:
        raw = pd.read_excel(force_path, header=None, nrows=1)
    except Exception:
        return {}

    meta = {}
    patterns = {
        "target_freq_hz": (7, r"Target freq \(Hz\):\s*([-\d.eE]+)"),
        "test_reported_achieved_freq_hz": (8, r"Achieved freq \(Hz, avg\):\s*([-\d.eE]+)"),
        "calibrated_depth_range_mm": (9, r"Calibrated depth range \(mm\):\s*([-\d.eE]+)"),
    }
    for key, (col_idx, pattern) in patterns.items():
        if col_idx >= raw.shape[1]:
            continue
        cell = raw.iat[0, col_idx]
        if not isinstance(cell, str):
            continue
        m = re.search(pattern, cell)
        if m:
            try:
                meta[key] = float(m.group(1))
            except ValueError:
                pass
    return meta


def _mark_peaks_on_ax(ax, peak_times: np.ndarray, trough_times: np.ndarray,
                       t_ref: np.ndarray, y_ref: np.ndarray,
                       peak_color: str = "red", trough_color: str = "dodgerblue",
                       marker_size: int = 40, label_prefix: str = ""):
    """Scatter-plot peak (▲) and trough (▼) markers onto an existing axes.

    t_ref / y_ref should be the same uniform grid that peak detection ran on
    — i.e. t_u / y_smooth returned by extract_cycle_metrics. This ensures
    markers sit cleanly on the spline curve rather than the noisier raw signal.
    """
    sort_idx = np.argsort(t_ref)
    t_s = t_ref[sort_idx]
    y_s = y_ref[sort_idx]

    if len(peak_times) > 0:
        peak_vals = np.interp(peak_times, t_s, y_s)
        lbl = f"{label_prefix} peaks ({len(peak_times)})".strip()
        ax.scatter(peak_times, peak_vals, color=peak_color, zorder=5,
                   s=marker_size, marker="^", label=lbl,
                   linewidths=0.5, edgecolors="white")

    if len(trough_times) > 0:
        trough_vals = np.interp(trough_times, t_s, y_s)
        lbl = f"{label_prefix} troughs ({len(trough_times)})".strip()
        ax.scatter(trough_times, trough_vals, color=trough_color, zorder=5,
                   s=marker_size, marker="v", label=lbl,
                   linewidths=0.5, edgecolors="white")


def plot_force(force_path: Path, out_dir: Path, default_expected_freq_hz: float,
               cycle_records: dict, sampling_rows: list,
               spline_s: float = None):
    df = pd.read_excel(force_path)

    raw_time_col    = find_column(df.columns, "time")
    since_start_col = find_column(df.columns, "since", "start")
    actual_col      = find_column(df.columns, "load cell") or find_column(df.columns, "force")
    position_col    = find_column(df.columns, "actual position")

    if raw_time_col is None or actual_col is None:
        print(f"  Could not find Time/Force columns in {force_path.name}: {list(df.columns)}")
        return []

    metadata = read_triangle_metadata(force_path)
    expected_freq_hz = metadata.get("target_freq_hz", default_expected_freq_hz)
    if "target_freq_hz" not in metadata:
        print(f"  [metadata] could not parse target freq from {force_path.name}, "
              f"falling back to default {default_expected_freq_hz} Hz")

    plot_time_col = since_start_col if since_start_col is not None else raw_time_col
    t = df[plot_time_col].to_numpy(dtype=float)
    sampling_rows.append(sampling_summary(force_path.name, t, expected_freq_hz))

    has_position = position_col is not None
    if has_position:
        fig, (ax, ax_pos) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                          gridspec_kw={"height_ratios": [2, 1]})
    else:
        fig, ax = plt.subplots(figsize=(11, 4.5))

    raw_alpha = 0.35 if spline_s is not None else 1.0
    ax.plot(df[plot_time_col], df[actual_col],
            label=f"{actual_col} (raw)", linewidth=0.9, alpha=raw_alpha)

    y = df[actual_col].to_numpy(dtype=float)
    periods, amplitudes, peak_times, trough_times, t_u, y_smooth = \
        extract_cycle_metrics(t, y, expected_freq_hz, spline_s=spline_s)

    extra = {}
    if "test_reported_achieved_freq_hz" in metadata and len(periods) > 0:
        peak_freq_mean = float((1.0 / periods).mean())
        extra["test_reported_achieved_freq_hz"] = metadata["test_reported_achieved_freq_hz"]
        extra["peak_detect_vs_reversal_diff_hz"] = round(
            peak_freq_mean - metadata["test_reported_achieved_freq_hz"], 5
        )
    if "calibrated_depth_range_mm" in metadata:
        extra["calibrated_depth_range_mm"] = metadata["calibrated_depth_range_mm"]

    freq_rows = [build_frequency_row(force_path.name, actual_col, periods,
                                      expected_freq_hz, extra=extra)]

    if spline_s is not None:
        ax.plot(t_u, y_smooth,
                label=f"{actual_col} (spline s={spline_s:.0f})",
                linewidth=1.8, linestyle="--",
                color="tab:red", alpha=0.92, zorder=4)

    _mark_peaks_on_ax(ax, peak_times, trough_times, t_u, y_smooth,
                      peak_color="red", trough_color="dodgerblue",
                      label_prefix=actual_col)

    for p in periods:
        cycle_records["period"][actual_col].append({"run": force_path.name, "value": p})
    for a in amplitudes:
        cycle_records["amplitude"][actual_col].append({"run": force_path.name, "value": a})

    ax.set_ylabel("Force (N)")
    spline_note = f" | spline s={spline_s:.0f}" if spline_s is not None else ""
    title_note = f" | target {expected_freq_hz:.3f} Hz"
    if "test_reported_achieved_freq_hz" in metadata:
        title_note += f" | reversal-based {metadata['test_reported_achieved_freq_hz']:.3f} Hz"
    ax.set_title(f"Force vs Time — {force_path.name}{spline_note}{title_note}")
    ax.legend(fontsize=8)

    if has_position:
        ax_pos.plot(df[plot_time_col], df[position_col], linewidth=0.9,
                    color="tab:green", label=position_col)
        ax_pos.set_ylabel("Position (mm)")
        ax_pos.set_xlabel(f"{plot_time_col}")
        ax_pos.legend(fontsize=8)
    else:
        ax.set_xlabel(f"{plot_time_col}")

    fig.tight_layout()

    out_path = out_dir / f"{force_path.stem}_force_vs_time.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")

    return freq_rows


def plot_caps(cap_path: Path, out_dir: Path, expected_freq_hz: float,
              cycle_records: dict, sampling_rows: list,
              spline_s: float = None):
    df = pd.read_excel(cap_path)

    time_col = find_column(df.columns, "time")
    if time_col is None:
        print(f"  Could not find a Time column in {cap_path.name}: {list(df.columns)}")
        return []

    cap_cols = [c for c in df.columns if str(c).upper().startswith("CAP")]
    cap_cols = sorted(cap_cols, key=lambda c: str(c).upper())[:8]

    if not cap_cols:
        print(f"  No CAP columns found in {cap_path.name}: {list(df.columns)}")
        return []

    t = df[time_col].to_numpy(dtype=float)
    sampling_rows.append(sampling_summary(cap_path.name, t, expected_freq_hz))

    fig, axes = plt.subplots(4, 2, figsize=(12, 12), sharex=True)
    axes = axes.flatten()

    freq_rows = []

    for i, ax in enumerate(axes):
        if i < len(cap_cols):
            col = cap_cols[i]
            y = df[col].to_numpy(dtype=float)

            raw_alpha = 0.35 if spline_s is not None else 1.0
            ax.plot(df[time_col], df[col], linewidth=0.8, color=f"C{i}",
                    label="raw", alpha=raw_alpha)

            periods, amplitudes, peak_times, trough_times, t_u, y_smooth = \
                extract_cycle_metrics(t, y, expected_freq_hz, spline_s=spline_s)
            freq_rows.append(build_frequency_row(cap_path.name, col, periods, expected_freq_hz))

            if spline_s is not None:
                ax.plot(t_u, y_smooth,
                        linewidth=1.5, linestyle="--", color="tab:orange",
                        alpha=0.95, label=f"spline s={spline_s:.0f}", zorder=4)

            _mark_peaks_on_ax(ax, peak_times, trough_times, t_u, y_smooth,
                              peak_color="red", trough_color="dodgerblue",
                              marker_size=30)

            ax.set_title(
                f"{col}  |  peaks: {len(peak_times)}  troughs: {len(trough_times)}",
                fontsize=9
            )
            ax.set_ylabel("pF", fontsize=8)
            ax.legend(fontsize=7, loc="upper right")

            for p in periods:
                cycle_records["period"][col].append({"run": cap_path.name, "value": p})
            for a in amplitudes:
                cycle_records["amplitude"][col].append({"run": cap_path.name, "value": a})
        else:
            ax.axis("off")
        if i >= 6:
            ax.set_xlabel(time_col)

    spline_note = f" | spline s={spline_s:.0f}" if spline_s is not None else ""
    fig.suptitle(f"CAP channels vs Time — {cap_path.name}{spline_note}")
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    out_path = out_dir / f"{cap_path.stem}_cap_vs_time.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")

    return freq_rows


def run_welch_anova(cycle_records: dict, metric: str):
    """Welch's ANOVA + eta-squared across runs, per signal."""
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
                "note": (f"zero/undefined variance in run(s) {list(bad_groups.index)}"
                         " - likely a flat/dead channel; Welch's ANOVA skipped"),
            })
            continue

        try:
            result = pg.welch_anova(data=df, dv="value", between="run")
            r = result.iloc[0]
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
    print("Triangle test analysis (folder mode, peak-to-peak frequency + run-to-run ANOVA)"
          " — press Enter to skip a folder.\n")

    force_folder = prompt_folder("Folder of Force/Load-cell triangle xlsx files: ")
    cap_folder   = prompt_folder("Folder of CAP/jlink xlsx files: ")

    freq_input = input(
        "Default expected frequency in Hz, used only if a file's own target freq "
        "can't be parsed from its metadata [default 5.0]: "
    ).strip()
    default_expected_freq_hz = float(freq_input) if freq_input else 5.0

    # Spline smoothing only applies to CAP channels — Force is low-noise
    # enough (and has sharp reversal apexes) that smoothing tends to shave
    # real peak amplitude rather than remove noise, so it's hardcoded off
    # for Force and never prompted for.
    force_spline_s = None

    print("\nSpline smoothing reduces noise before peak detection (CAP channels only —")
    print("Force is left unsmoothed).")
    print("  s = smoothing factor — larger = smoother, smaller = closer to raw signal.")
    print("  Good starting range: 1× to 10× the number of samples in your signal.")
    print("  Enter 0 or leave blank to disable (use raw signal, same as before).\n")
    spline_input = input("CAP spline smoothing factor s [0 / Enter = disable]: ").strip()
    try:
        s_val = float(spline_input) if spline_input else 0.0
    except ValueError:
        s_val = 0.0
    if s_val <= 0:
        cap_spline_s = None
        print("  Spline disabled — raw resampled signal used for CAP peak detection.")
    else:
        cap_spline_s = s_val
        print(f"  CAP spline smoothing enabled: s = {cap_spline_s:.0f}")

    out_dir = Path("./triangle_analysis_output")
    out_dir.mkdir(exist_ok=True)

    freq_rows     = []
    sampling_rows = []
    cycle_records = {"period": defaultdict(list), "amplitude": defaultdict(list)}

    if force_folder is not None:
        force_files = list_xlsx_files(force_folder)
        if not force_files:
            print(f"  No xlsx files found in {force_folder}")
        for f in force_files:
            print(f"Processing {f.name}...")
            freq_rows.extend(plot_force(f, out_dir, default_expected_freq_hz, cycle_records,
                                         sampling_rows, spline_s=force_spline_s))

    if cap_folder is not None:
        cap_files = list_xlsx_files(cap_folder)
        if not cap_files:
            print(f"  No xlsx files found in {cap_folder}")
        for f in cap_files:
            print(f"Processing {f.name}...")
            freq_rows.extend(plot_caps(f, out_dir, default_expected_freq_hz, cycle_records,
                                        sampling_rows, spline_s=cap_spline_s))

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