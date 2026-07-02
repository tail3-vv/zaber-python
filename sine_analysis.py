"""
analyze_sine_run.py

Standalone analysis script for the sine-wave synchronization test.
Prompts for the Force (Zaber/Futek) run xlsx and the CAP/ACC (jlink) run
xlsx, then plots and saves:
  - Force vs Time (actual force, plus the target/reference curve if present)
  - CAP vs Time: 8 subplots, one per capacitance channel

If the force file has a "Time since test start (s)" column (i.e. it was
produced by the updated run_sine_test), that column is used for the Force
plot's x-axis, and the same offset is used to trim the CAP file's leading
calibration dead-time and align its x-axis to the same zero point.
Otherwise both files fall back to their raw "Time (s)" columns as-is.

Run directly:
    python analyze_sine_run.py

Requires: pandas, matplotlib, openpyxl
"""
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def find_column(columns, *keywords):
    """Return the first column whose name contains all given keywords (case-insensitive)."""
    for col in columns:
        lowered = col.lower()
        if all(k.lower() in lowered for k in keywords):
            return col
    return None


def plot_force(force_path: Path, out_dir: Path):
    """Returns the test-start offset (raw_time - since_start_time) if the
    file has both columns, else None."""
    df = pd.read_excel(force_path)

    raw_time_col = find_column(df.columns, "time")
    since_start_col = find_column(df.columns, "since", "start")
    actual_col = find_column(df.columns, "load cell") or find_column(df.columns, "force")
    target_col = find_column(df.columns, "target")

    if raw_time_col is None or actual_col is None:
        print(f"  Could not find Time/Force columns in {force_path.name}: {list(df.columns)}")
        return None

    plot_time_col = since_start_col if since_start_col is not None else raw_time_col
    offset = None
    if since_start_col is not None:
        offset = (df[raw_time_col] - df[since_start_col]).median()

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

    return offset


def plot_caps(cap_path: Path, out_dir: Path, time_offset: float = None):
    df = pd.read_excel(cap_path)

    time_col = find_column(df.columns, "time")
    if time_col is None:
        print(f"  Could not find a Time column in {cap_path.name}: {list(df.columns)}")
        return

    cap_cols = [c for c in df.columns if c.upper().startswith("CAP")]
    cap_cols = sorted(cap_cols, key=lambda c: c.upper())[:8]

    if not cap_cols:
        print(f"  No CAP columns found in {cap_path.name}: {list(df.columns)}")
        return

    plot_df = df
    x_label = time_col
    if time_offset is not None:
        # trim the leading calibration dead-time and zero the x-axis to match
        # the force plot's "time since test start"
        plot_df = df[df[time_col] >= time_offset].copy()
        plot_df["_aligned_time"] = plot_df[time_col] - time_offset
        x_col = "_aligned_time"
        x_label = "Time since test start (s)"
        print(f"  Trimmed {len(df) - len(plot_df)} leading rows "
              f"({time_offset:.2f}s of calibration dead-time)")
    else:
        x_col = time_col

    fig, axes = plt.subplots(4, 2, figsize=(12, 12), sharex=True)
    axes = axes.flatten()

    for i, ax in enumerate(axes):
        if i < len(cap_cols):
            col = cap_cols[i]
            ax.plot(plot_df[x_col], plot_df[col], linewidth=0.8, color=f"C{i}")
            ax.set_title(col, fontsize=10)
            ax.set_ylabel("pF", fontsize=8)
        else:
            ax.axis("off")
        if i >= 6:
            ax.set_xlabel(x_label)

    fig.suptitle(f"CAP channels vs Time — {cap_path.name}")
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    out_path = out_dir / f"{cap_path.stem}_cap_vs_time.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def main():
    print("Sine test analysis — enter the xlsx file paths (press Enter to skip a file).\n")

    force_input = input("Force/Load-cell xlsx path: ").strip().strip('"').strip("'")
    cap_input = input("CAP/jlink xlsx path: ").strip().strip('"').strip("'")

    out_dir = Path("./sine_analysis_output")
    out_dir.mkdir(exist_ok=True)

    time_offset = None

    if force_input:
        force_path = Path(force_input)
        if force_path.is_file():
            time_offset = plot_force(force_path, out_dir)
        else:
            print(f"  Force file not found: {force_path}")

    if cap_input:
        cap_path = Path(cap_input)
        if cap_path.is_file():
            plot_caps(cap_path, out_dir, time_offset=time_offset)
        else:
            print(f"  CAP file not found: {cap_path}")

    print(f"\nDone. Plots saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()