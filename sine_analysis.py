"""
analyze_sine_run.py

Standalone analysis script for the sine-wave synchronization test.
Prompts for the Force (Zaber/Futek) run xlsx and the CAP/ACC (jlink) run
xlsx, then plots and saves:
  - Force vs Time (actual force, plus the target/reference curve if present)
  - CAP vs Time: 8 subplots, one per capacitance channel

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
    df = pd.read_excel(force_path)

    time_col = find_column(df.columns, "time")
    actual_col = find_column(df.columns, "load cell") or find_column(df.columns, "force")
    target_col = find_column(df.columns, "target")

    if time_col is None or actual_col is None:
        print(f"  Could not find Time/Force columns in {force_path.name}: {list(df.columns)}")
        return

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(df[time_col], df[actual_col], label=actual_col, linewidth=0.9)
    if target_col is not None:
        ax.plot(df[time_col], df[target_col], label=target_col, alpha=0.7, linewidth=0.9)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Force (N)")
    ax.set_title(f"Force vs Time — {force_path.name}")
    ax.legend()
    fig.tight_layout()

    out_path = out_dir / f"{force_path.stem}_force_vs_time.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_caps(cap_path: Path, out_dir: Path):
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
            ax.set_xlabel("Time (s)")

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

    if force_input:
        force_path = Path(force_input)
        if force_path.is_file():
            plot_force(force_path, out_dir)
        else:
            print(f"  Force file not found: {force_path}")

    if cap_input:
        cap_path = Path(cap_input)
        if cap_path.is_file():
            plot_caps(cap_path, out_dir)
        else:
            print(f"  CAP file not found: {cap_path}")

    print(f"\nDone. Plots saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()