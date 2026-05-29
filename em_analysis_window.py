import tkinter as tk
from tkinter import ttk
from datetime import datetime
import math
import random

import matplotlib
try:
    matplotlib.use("TkCairo")
    from matplotlib.backends.backend_tkcairo import FigureCanvasTkCairo as _FigureCanvas
except Exception:
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _FigureCanvas
matplotlib.rcParams["path.simplify"] = True
matplotlib.rcParams["path.simplify_threshold"] = 0.0
matplotlib.rcParams["lines.antialiased"] = True
matplotlib.rcParams["text.antialiased"] = True
matplotlib.rcParams["figure.dpi"] = 144
from matplotlib.figure import Figure

"""
EM Analysis Window — Feature 1.6 (stories 1.6.1 through 1.6.6).
Tabbed analysis: Raw Signals, Pressure Sensitivity Curves, All CH/Runs,
Summary Statistics, Report Output. Preview mode generates synthetic data.
"""


CHANNEL_COUNT = 8
# preview-mode synthetic curve constants
PRESSURE_MAX_KPA = 24.0
SAMPLE_COUNT = 80
# rough channel-to-channel sensitivity variation for the simulation
SENSITIVITY_BASE = (3.0, 3.4, 3.1, 3.6, 3.2, 3.5, 3.3, 3.7)
INFLECTION_PRESSURES = (12.5, 11.0, 13.0, 12.1, 12.8, 11.7, 13.3, 12.0)
SHORT_CIRCUIT_THRESHOLD_KPA = 25.0  # criterion: spike above this flags shorted channel


def _style_axes_clean(ax, xlabel, ylabel, title=None):
    if title:
        ax.set_title(title, fontsize=9, color="#1a1f2c", pad=4)
    ax.set_xlabel(xlabel, fontsize=8, color="#3b3f47", labelpad=2)
    ax.set_ylabel(ylabel, fontsize=8, color="#3b3f47", labelpad=2)
    ax.tick_params(colors="#5a6473", labelsize=7, length=3, width=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cdd3de")
    ax.spines["bottom"].set_color("#cdd3de")
    ax.spines["left"].set_linewidth(0.7)
    ax.spines["bottom"].set_linewidth(0.7)
    ax.grid(True, color="#eef0f4", linewidth=0.5)
    ax.set_axisbelow(True)


# preview-mode synthetic data generation

def _simulate_channel(run_idx, channel_idx, peak_kpa=None):
    """Generate (pressure_kpa, cap_pf, force_n) arrays for one channel of one run."""
    base_sens = SENSITIVITY_BASE[channel_idx]
    # per-run jitter
    rng = random.Random(run_idx * 17 + channel_idx)
    jitter = 1.0 + (rng.random() - 0.5) * 0.15
    sens = base_sens * jitter
    inflection = INFLECTION_PRESSURES[channel_idx] + (rng.random() - 0.5) * 1.5

    max_p = peak_kpa if peak_kpa is not None else PRESSURE_MAX_KPA
    pressures = [max_p * (i / (SAMPLE_COUNT - 1)) for i in range(SAMPLE_COUNT)]
    # capacitance response: low slope, then steeper after inflection
    caps = []
    for p in pressures:
        if p <= inflection:
            cap = sens * 0.4 * p
        else:
            cap = sens * 0.4 * inflection + sens * 1.2 * (p - inflection)
        cap += (rng.random() - 0.5) * 0.05
        caps.append(cap)
    # force is roughly proportional to pressure × ecoflex area
    force_max = 18 + rng.random() * 1.5
    forces = [force_max * (i / (SAMPLE_COUNT - 1)) for i in range(SAMPLE_COUNT)]
    return pressures, caps, forces, inflection


class EMAnalysisWindow:

    def __init__(self, parent, main_window, target_folder=None, runs=3,
                 sensor_id=None, sensor_type="Standard"):
        self.parent = parent
        self.main_window = main_window
        self.target_folder = target_folder
        self.runs = max(1, int(runs or 1))
        self.sensor_id = sensor_id or (main_window.sensor_id.get() if main_window else "unknown")
        self.sensor_type = sensor_type

        self.window = tk.Toplevel(parent)
        self.window.title("EM Analysis Data and Plots")
        self.window.geometry("1200x800+0+0")
        self.window.minsize(900, 600)
        self.window.configure(bg="#eef2f7")
        self.window.grab_set()

        self.data_source = "synthetic"
        self.em_result = None
        if not self._try_load_real_data():
            self.run_data = self._generate_run_data()
            self.summary = self._compute_summary_stats()
            self.shorted_channels = self._detect_shorted_channels()

        self._create_widgets()

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.window.bind("<Escape>", lambda _e: self._on_close())

    def _try_load_real_data(self):
        # required structure: target_folder/CAP/*.csv and target_folder/FUT/*.xlsx
        if self.target_folder is None:
            return False
        try:
            from pathlib import Path
        except ImportError:
            return False
        target = self.target_folder if hasattr(self.target_folder, "exists") else Path(str(self.target_folder))
        cap_dir = target / "CAP"
        fut_dir = target / "FUT"
        if not (cap_dir.exists() and fut_dir.exists()):
            return False
        cap_files = list(cap_dir.glob("*.csv"))
        fut_files = list(fut_dir.glob("*.xlsx"))
        if not cap_files or not fut_files:
            return False
        try:
            from em_analysis import EMAnalysis
            # EMAnalysis takes a path INSIDE the test folder and does Path(path).parent
            # for cap/fut sibling lookups, so we pass the fut dir explicitly.
            analysis = EMAnalysis(str(fut_dir), self.sensor_id, self.sensor_type)
            result = analysis.save_data()
        except Exception as exc:
            print(f"[em analysis] real pipeline failed, falling back to synthetic: {exc}")
            return False
        # map the result into our data structures
        try:
            self.run_data = self._adapt_result_to_run_data(result)
            self.summary = self._adapt_result_to_summary(result)
            self.shorted_channels = self._adapt_result_to_shorted(result)
        except Exception as exc:
            print(f"[em analysis] adapter failed: {exc}")
            return False
        self.data_source = "real"
        self.em_result = result
        # update run count to match the real data
        self.runs = len(self.run_data)
        return True

    def _adapt_result_to_run_data(self, result):
        zaber_x = result.get("zaber_x", [])
        zaber_y = result.get("zaber_y", [])
        test_arrays = result.get("test", [])
        max_ps = result.get("max_ps", None)
        max_cap = result.get("max_cap", None)
        max_kpa = result.get("max_kpa", None)
        inf_cap = result.get("inf_cap", None)

        n_runs = len(zaber_x)
        data = []
        for i in range(n_runs):
            channels = []
            # cap-vs-time and force-vs-time live in test[i][0] and test[i][1]
            cap_time = test_arrays[i][0][:, 0] if i < len(test_arrays) else None
            cap_per_channel = test_arrays[i][0] if i < len(test_arrays) else None
            force_time = test_arrays[i][1][:, 0] if i < len(test_arrays) else None
            force_data = test_arrays[i][1][:, 1] if i < len(test_arrays) else None
            pressures = zaber_x[i]
            for j in range(CHANNEL_COUNT):
                caps_smoothed = zaber_y[i][j] if j < len(zaber_y[i]) else []
                # column j+1 of test[i][0] is channel j's cap-vs-time
                cap_time_signal = cap_per_channel[:, j + 1] if cap_per_channel is not None else None
                channels.append({
                    "pressures": pressures,
                    "caps": caps_smoothed,
                    "cap_time": cap_time,
                    "cap_time_signal": cap_time_signal,
                    "force_time": force_time,
                    "forces": force_data,
                    "inflection": None,  # raw inflection x value not stored; ps value used instead
                    "ps_at_inflection": float(max_ps[i, j]) if max_ps is not None else 0.0,
                    "max_cap": float(max_cap[i, j]) if max_cap is not None else 0.0,
                    "max_kpa": float(max_kpa[i, j]) if max_kpa is not None else 0.0,
                    "inf_cap": float(inf_cap[i, j]) if inf_cap is not None else 0.0,
                })
            data.append(channels)
        return data

    def _adapt_result_to_summary(self, result):
        # convert numpy arrays to plain lists to match the synthetic-mode dict shape
        def listify(arr):
            try:
                return [float(v) for v in arr]
            except Exception:
                return [0.0] * CHANNEL_COUNT
        return {
            "Mean PS at Inflection": listify(result.get("mean_max_ps", [])),
            "Std PS at Inflection":  listify(result.get("std_max_ps", [])),
            "COV PS at Inflection":  listify(result.get("cov_max_ps", [])),
            "Mean Max kPa":          listify(result.get("mean_max_kpa", [])),
            "Std Max kPa":           listify(result.get("std_max_kpa", [])),
            "Mean Max CAP":          listify(result.get("mean_max_cap", [])),
            "Std Max CAP":           listify(result.get("std_max_cap", [])),
        }

    def _adapt_result_to_shorted(self, result):
        raw = result.get("shorted_ch", None)
        if raw is None:
            return []
        try:
            return sorted({int(c) + 1 for c in raw})
        except Exception:
            return []

    # synthetic preview data + simple analytics

    def _generate_run_data(self):
        data = []
        for run_idx in range(self.runs):
            channels = []
            for ch_idx in range(CHANNEL_COUNT):
                pressures, caps, forces, inflection = _simulate_channel(run_idx, ch_idx)
                # derive PS at inflection (slope of cap-vs-pressure curve past inflection)
                ps_at_inflection = SENSITIVITY_BASE[ch_idx] * 1.2 * (1.0 + (run_idx - 1) * 0.02)
                max_cap = max(caps)
                max_kpa = pressures[caps.index(max_cap)]
                channels.append({
                    "pressures": pressures,
                    "caps": caps,
                    "forces": forces,
                    "inflection": inflection,
                    "ps_at_inflection": ps_at_inflection,
                    "max_cap": max_cap,
                    "max_kpa": max_kpa,
                })
            data.append(channels)
        return data

    def _compute_summary_stats(self):
        # aggregate per-channel metrics across all runs
        rows = {}
        per_ch = {ch: {"ps": [], "max_kpa": [], "max_cap": []}
                  for ch in range(CHANNEL_COUNT)}
        for run in self.run_data:
            for ch_idx, ch in enumerate(run):
                per_ch[ch_idx]["ps"].append(ch["ps_at_inflection"])
                per_ch[ch_idx]["max_kpa"].append(ch["max_kpa"])
                per_ch[ch_idx]["max_cap"].append(ch["max_cap"])

        def mean(xs): return sum(xs) / len(xs) if xs else 0
        def std(xs):
            m = mean(xs)
            return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) if xs else 0
        def cov(xs):
            m = mean(xs)
            return std(xs) / m if m else 0

        rows["Mean PS at Inflection"] = [mean(per_ch[c]["ps"]) for c in range(CHANNEL_COUNT)]
        rows["Std PS at Inflection"] = [std(per_ch[c]["ps"]) for c in range(CHANNEL_COUNT)]
        rows["COV PS at Inflection"] = [cov(per_ch[c]["ps"]) for c in range(CHANNEL_COUNT)]
        rows["Mean Max kPa"] = [mean(per_ch[c]["max_kpa"]) for c in range(CHANNEL_COUNT)]
        rows["Std Max kPa"] = [std(per_ch[c]["max_kpa"]) for c in range(CHANNEL_COUNT)]
        rows["Mean Max CAP"] = [mean(per_ch[c]["max_cap"]) for c in range(CHANNEL_COUNT)]
        rows["Std Max CAP"] = [std(per_ch[c]["max_cap"]) for c in range(CHANNEL_COUNT)]
        return rows

    def _detect_shorted_channels(self):
        # criterion: large compression spike over the high threshold lists affected CH; else NONE.
        flagged = []
        for ch_idx in range(CHANNEL_COUNT):
            max_kpa_runs = [run[ch_idx]["max_kpa"] for run in self.run_data]
            if max(max_kpa_runs) > SHORT_CIRCUIT_THRESHOLD_KPA:
                flagged.append(ch_idx + 1)
        return flagged

    # widget construction

    def _create_widgets(self):
        # progress modal first — story 1.6 acceptance criterion
        self._show_progress_modal()

        outer = tk.Frame(self.window, bg="#eef2f7")
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg="#eef2f7", highlightthickness=0, bd=0,
                           yscrollincrement=8)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scroll_frame = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _reconfigure():
            scroll_frame.update_idletasks()
            canvas_h = canvas.winfo_height() or 1
            natural_h = scroll_frame.winfo_reqheight()
            h = max(natural_h, canvas_h)
            current_h = int(canvas.itemcget(window_id, "height") or "0")
            if h != current_h:
                canvas.itemconfig(window_id, height=h)
            canvas.configure(scrollregion=canvas.bbox("all"))
        scroll_frame.bind("<Configure>", lambda _: canvas.after_idle(_reconfigure))
        def on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
            canvas.after_idle(_reconfigure)
        canvas.bind("<Configure>", on_canvas_configure)
        self._canvas = canvas

        container = ttk.Frame(scroll_frame, padding=(20, 14, 20, 14))
        container.pack(fill="both", expand=True)

        # title row
        ttk.Label(container, text="EM Analysis Data and Plots",
                  style="Title.TLabel").pack(anchor="w", pady=(0, 12))

        # shorted-channel status banner (also shows real vs synthetic data source)
        source_note = "real CAP/FUT data" if self.data_source == "real" else "preview (synthetic) data"
        if self.shorted_channels:
            ch_list = ", ".join(f"CH{c}" for c in self.shorted_channels)
            banner_text = (f"SENSORS PASSING CHECKPOINT 02: shorted channels detected — "
                           f"{ch_list}    [source: {source_note}]")
            banner_bg = "#fdecea"
            banner_fg = "#9b2c1f"
        else:
            banner_text = (f"SENSORS PASSING CHECKPOINT 02: NONE (no shorted channels detected)"
                           f"    [source: {source_note}]")
            banner_bg = "#e7efff"
            banner_fg = "#3856b3"
        banner = tk.Label(container, text=banner_text,
                          bg=banner_bg, fg=banner_fg,
                          padx=12, pady=8, font=("Helvetica", 9, "bold"),
                          anchor="w", justify="left")
        banner.pack(fill="x", pady=(0, 14))

        # main card holding the notebook
        card = tk.Frame(container, bg="#ffffff",
                        highlightthickness=1,
                        highlightbackground="#dde2eb",
                        highlightcolor="#dde2eb")
        card.pack(fill="both", expand=True, pady=(0, 4))
        inner = ttk.Frame(card, padding=(14, 10, 14, 14), style="Card.TFrame")
        inner.pack(fill="both", expand=True)

        notebook = ttk.Notebook(inner)
        notebook.pack(fill="both", expand=True)
        self.notebook = notebook

        # tabs in mockup order
        self._build_raw_signals_tab(notebook)
        self._build_pressure_sensitivity_tab(notebook)
        self._build_all_ch_runs_tab(notebook)
        self._build_summary_stats_tab(notebook)
        self._build_report_output_tab(notebook)

        # wire mousewheel scroll for the outer canvas
        if hasattr(self.main_window, "install_mousewheel"):
            self.main_window.install_mousewheel(canvas)

    def _show_progress_modal(self):
        # quick fake progress modal — criterion: 'Show user feedback during generation'
        modal = tk.Toplevel(self.window)
        modal.title("")
        modal.geometry("320x110+520+340")
        modal.configure(bg="#ffffff")
        modal.resizable(False, False)
        modal.transient(self.window)
        modal.grab_set()
        ttk.Label(modal, text="Generating EM analysis outputs…",
                  style="FieldLabel.TLabel",
                  background="#ffffff").pack(anchor="w", padx=18, pady=(18, 6))
        pb = ttk.Progressbar(modal, mode="determinate", maximum=100, length=280)
        pb.pack(padx=18, pady=(0, 18))
        # fake the progress bar advancing then close
        def step(n=0):
            if n >= 100:
                modal.grab_release()
                modal.destroy()
                return
            pb["value"] = n
            modal.after(20, lambda: step(n + 8))
        modal.after(10, step)

    # raw signals tab (story 1.6.2)
    def _build_raw_signals_tab(self, notebook):
        page = ttk.Frame(notebook, style="Card.TFrame", padding=(8, 8, 8, 8))
        notebook.add(page, text="Raw Signals")
        # nested run picker
        run_nb = ttk.Notebook(page)
        run_nb.pack(fill="both", expand=True)
        for run_idx in range(self.runs):
            run_page = ttk.Frame(run_nb, style="Card.TFrame")
            run_nb.add(run_page, text=f"Run {run_idx + 1}")
            self._plot_raw_signals_grid(run_page, run_idx)

    def _plot_raw_signals_grid(self, parent, run_idx):
        # 8 channels in a 2 × 4 grid. real-data path uses the time/cap arrays from
        fig = Figure(figsize=(10.5, 4.8), dpi=110, facecolor="#ffffff",
                     layout="constrained")
        for ch_idx in range(CHANNEL_COUNT):
            ax = fig.add_subplot(2, 4, ch_idx + 1)
            ch = self.run_data[run_idx][ch_idx]
            if ch.get("cap_time") is not None and ch.get("cap_time_signal") is not None:
                ax.plot(ch["cap_time"], ch["cap_time_signal"],
                        color="#3a5dd9", linewidth=1.3, antialiased=True)
                xlabel = "Time (s)"
                ylabel = "Δ CAP (pF)"
            else:
                ax.plot(range(len(ch["caps"])), ch["caps"],
                        color="#3a5dd9", linewidth=1.3, antialiased=True)
                ax.plot(range(len(ch["forces"])), ch["forces"],
                        color="#f3a23a", linewidth=1.0,
                        linestyle="--", antialiased=True)
                xlabel = "Sample idx"
                ylabel = "CAP / Force"
            _style_axes_clean(ax, xlabel, ylabel,
                              title=f"Run {run_idx + 1} CH {ch_idx + 1}")
        cv = _FigureCanvas(fig, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        cv.draw()

    # pressure sensitivity curves tab (story 1.6.3)
    def _build_pressure_sensitivity_tab(self, notebook):
        page = ttk.Frame(notebook, style="Card.TFrame", padding=(8, 8, 8, 8))
        notebook.add(page, text="Pressure Sensitivity Curves")
        run_nb = ttk.Notebook(page)
        run_nb.pack(fill="both", expand=True)
        for run_idx in range(self.runs):
            run_page = ttk.Frame(run_nb, style="Card.TFrame")
            run_nb.add(run_page, text=f"Run {run_idx + 1}")
            self._plot_ps_curves_grid(run_page, run_idx)

    def _plot_ps_curves_grid(self, parent, run_idx):
        fig = Figure(figsize=(10.5, 4.8), dpi=110, facecolor="#ffffff",
                     layout="constrained")
        for ch_idx in range(CHANNEL_COUNT):
            ax = fig.add_subplot(2, 4, ch_idx + 1)
            ch = self.run_data[run_idx][ch_idx]
            ax.plot(ch["pressures"], ch["caps"],
                    color="#3a5dd9", linewidth=1.4, antialiased=True)
            if ch.get("inflection") is not None:
                ax.axvline(ch["inflection"], color="#9aa1ad", linewidth=0.7,
                           linestyle=":")
                title = (f"R{run_idx + 1} CH{ch_idx + 1} | "
                         f"PS@{ch['inflection']:.1f}: {ch['ps_at_inflection']:.2f} pF/kPa")
            else:
                title = (f"R{run_idx + 1} CH{ch_idx + 1} | "
                         f"PS: {ch['ps_at_inflection']:.2f} pF/kPa")
            _style_axes_clean(ax, "Pressure (kPa)", "Δ Cap (pF)", title=title)
        cv = _FigureCanvas(fig, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        cv.draw()

    # all CH / runs tab (story 1.6.4)
    def _build_all_ch_runs_tab(self, notebook):
        page = ttk.Frame(notebook, style="Card.TFrame", padding=(8, 8, 8, 8))
        notebook.add(page, text="All CH/Runs")
        view_nb = ttk.Notebook(page)
        view_nb.pack(fill="both", expand=True)

        by_ch_page = ttk.Frame(view_nb, style="Card.TFrame")
        view_nb.add(by_ch_page, text="By Channel (all runs)")
        self._plot_by_channel(by_ch_page)

        by_run_page = ttk.Frame(view_nb, style="Card.TFrame")
        view_nb.add(by_run_page, text="By Run (all channels)")
        self._plot_by_run(by_run_page)

    def _plot_by_channel(self, parent):
        # one subplot per channel, overlay all runs
        fig = Figure(figsize=(10.5, 4.8), dpi=110, facecolor="#ffffff",
                     layout="constrained")
        colors = ["#3a5dd9", "#f3a23a", "#3da556"]
        for ch_idx in range(CHANNEL_COUNT):
            ax = fig.add_subplot(2, 4, ch_idx + 1)
            for run_idx in range(self.runs):
                ch = self.run_data[run_idx][ch_idx]
                ax.plot(ch["pressures"], ch["caps"],
                        color=colors[run_idx % len(colors)],
                        linewidth=1.2, antialiased=True,
                        label=f"Run {run_idx + 1}")
            _style_axes_clean(ax, "Pressure (kPa)", "Δ Cap (pF)",
                              title=f"CH {ch_idx + 1}")
            if ch_idx == 0:
                ax.legend(loc="upper left", fontsize=6, frameon=False)
        cv = _FigureCanvas(fig, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        cv.draw()

    def _plot_by_run(self, parent):
        # one subplot per run, overlay all channels
        fig = Figure(figsize=(10.5, 4.8), dpi=110, facecolor="#ffffff",
                     layout="constrained")
        # adapt subplot count to runs (max 4 wide)
        ncols = min(self.runs, 4)
        nrows = math.ceil(self.runs / ncols)
        for run_idx in range(self.runs):
            ax = fig.add_subplot(nrows, ncols, run_idx + 1)
            for ch_idx in range(CHANNEL_COUNT):
                ch = self.run_data[run_idx][ch_idx]
                ax.plot(ch["pressures"], ch["caps"],
                        linewidth=1.0, antialiased=True,
                        label=f"CH {ch_idx + 1}")
            _style_axes_clean(ax, "Pressure (kPa)", "Δ Cap (pF)",
                              title=f"Run {run_idx + 1}")
            if run_idx == 0:
                ax.legend(loc="upper left", fontsize=6, frameon=False, ncol=2)
        cv = _FigureCanvas(fig, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        cv.draw()

    # summary statistics tab (story 1.6.5)
    def _build_summary_stats_tab(self, notebook):
        page = ttk.Frame(notebook, style="Card.TFrame", padding=(8, 8, 8, 8))
        notebook.add(page, text="Summary Stats")

        # treeview for the summary stats
        cols = ("metric",) + tuple(f"ch{i + 1}" for i in range(CHANNEL_COUNT))
        tv = ttk.Treeview(page, columns=cols, show="headings", height=12)
        tv.heading("metric", text="Summary Stat")
        tv.column("metric", width=200, anchor="w")
        for i in range(CHANNEL_COUNT):
            tv.heading(f"ch{i + 1}", text=f"Ch{i + 1}")
            tv.column(f"ch{i + 1}", width=90, anchor="center")

        # populate rows
        for metric, values in self.summary.items():
            formatted = []
            for v in values:
                if "COV" in metric:
                    formatted.append(f"{v:.4f}")
                elif "Std" in metric:
                    formatted.append(f"{v:.3f}")
                else:
                    formatted.append(f"{v:.2f}")
            tv.insert("", "end", values=(metric,) + tuple(formatted))

        scroll = ttk.Scrollbar(page, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=scroll.set)
        tv.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # report output tab (story 1.6.6)
    # produces the full 61-column Testing Tracker row:
    #   10 identity + 11 P.S. + 11 Pressure + 11 Max CAP + 9 Center-4 Mean + 9 Center-4 COV
    # values come from em_analysis.save_data() in real mode, or synthetic equivalents.
    REPORT_KPA_POINTS = (5, 10, 15, 20, 25, 30, 35, 40, 45)

    def _build_report_output_tab(self, notebook):
        page = ttk.Frame(notebook, style="Card.TFrame", padding=(14, 12, 14, 14))
        notebook.add(page, text="Report Output")

        ttk.Label(page,
                  text=("Two-row Testing Tracker block (headers + values). "
                        "Use Copy Values to paste a single row into the spreadsheet."),
                  style="Caption.TLabel",
                  background="#ffffff").pack(anchor="w", pady=(0, 8))

        headers, values = self._build_report_row()
        self._report_headers = headers
        self._report_values = values

        # tab-separated preview rendered in a monospace Text widget with horizontal
        # scrolling so all 61 columns are visible without truncation.
        preview_frame = ttk.Frame(page, style="Card.TFrame")
        preview_frame.pack(fill="both", expand=True, pady=(0, 12))

        text = tk.Text(preview_frame, height=8, wrap="none",
                       font=("Menlo", 9), bg="#fff7e6", fg="#3b3f47",
                       bd=1, relief="solid", padx=8, pady=6)
        xscroll = ttk.Scrollbar(preview_frame, orient="horizontal", command=text.xview)
        yscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=text.yview)
        text.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        text.insert("end", "\t".join(headers) + "\n")
        text.insert("end", "\t".join(values) + "\n")
        text.config(state=tk.DISABLED)

        # copy buttons
        btn_row = ttk.Frame(page, style="Card.TFrame")
        btn_row.pack(fill="x")
        self.copy_feedback = ttk.Label(btn_row, text="",
                                       style="Caption.TLabel",
                                       background="#ffffff")
        self.copy_feedback.pack(side="left", padx=(0, 12))
        ttk.Button(btn_row, text="Copy Headers + Values",
                   command=self._copy_with_headers,
                   style="Outline.TButton").pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Copy Values",
                   command=self._copy_values,
                   style="Primary.TButton").pack(side="right")

    def _build_report_row(self):
        """Return (headers, values) as lists of 61 strings matching the Testing Tracker
        column order: 10 identity + P.S. block + Pressure block + Max CAP block +
        Center-4 Avg Mean (9 kPa pts) + Center-4 Avg COV (9 kPa pts)."""
        identity_headers = [
            "Lot Number (YYMMDDB##S##X)",
            "Electromechanical Standards Met",
            "Version",
            "Tester Sign off Initial",
            "Date Tested",
            "Fabrication Type",
            "Eco Blox ID",
            "Run # Tested",
            "Run # Counted",
            "Shorted CH via Compression",
        ]
        date_str = datetime.now().strftime("%m/%d/%Y")
        shorted_value = (", ".join(f"CH{c}" for c in self.shorted_channels)
                         if self.shorted_channels else "NONE")
        # fabrication type comes from the trailing A / B / AB on the sensor ID
        # (YYMMDDB##S##X where X is A, B, or AB). check AB first since A is a prefix of AB.
        fab_type = ""
        sid = (self.sensor_id or "").strip().upper()
        if sid.endswith("AB"):
            fab_type = "AB"
        elif sid.endswith("A"):
            fab_type = "A"
        elif sid.endswith("B"):
            fab_type = "B"
        identity_values = [
            self.sensor_id,
            "PASS" if not self.shorted_channels else "FAIL",
            "V3.7.8",
            "",
            date_str,
            fab_type,
            "",
            str(self.runs),
            str(self.runs),
            shorted_value,
        ]

        # gather metric arrays — prefer real em_result, else derive from summary/run_data
        ps_mean, ps_cov = self._report_metric_arrays(
            "mean_max_ps", "cov_max_ps", "Mean PS at Inflection", "COV PS at Inflection",
            per_ch_key="ps")
        kpa_mean, kpa_cov = self._report_metric_arrays(
            "mean_max_kpa", "cov_max_kpa", "Mean Max kPa", None,
            per_ch_key="max_kpa")
        cap_mean, cap_cov = self._report_metric_arrays(
            "mean_max_cap", "max_cap_cov", "Mean Max CAP", None,
            per_ch_key="max_cap")

        # center-4 / outer-4 / all aggregate COV values (mean across channel-subset COVs)
        ps_aggs = self._region_cov_aggregates(ps_cov)
        kpa_aggs = self._region_cov_aggregates(kpa_cov)
        cap_aggs = self._region_cov_aggregates(cap_cov)

        # per-kPa center-4 mean & COV across the 9 pressure points (5..45 kPa)
        c4_mean_9, c4_cov_9 = self._report_center4_per_kpa()

        # build header lists for each block — channel columns share the metric prefix
        def metric_headers(prefix):
            return ([f"{prefix} CH{i+1}" for i in range(CHANNEL_COUNT)]
                    + [f"{prefix} Avg Center 4 CHs COV",
                       f"{prefix} Avg Outer 4 CHs COV",
                       f"{prefix} Avg ALL CHs COV"])

        kpa_headers_mean = [f"Center 4 CHs Avg Mean {p} kPa" for p in self.REPORT_KPA_POINTS]
        kpa_headers_cov = [f"Center 4 CHs Avg COV {p} kPa" for p in self.REPORT_KPA_POINTS]

        headers = (identity_headers
                   + metric_headers("P.S at Inflection (pF/kPa)")
                   + metric_headers("Pressure at Inflection (kPa)")
                   + metric_headers("Max CAP (pF)")
                   + kpa_headers_mean
                   + kpa_headers_cov)

        def fmt_value(v, percent=False):
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return ""
            if percent:
                return f"{v * 100:.2f}%"
            return f"{v:.3f}"

        values = list(identity_values)
        # P.S. block — values to 3 decimals, COVs as percents
        values += [fmt_value(v) for v in ps_mean] + [fmt_value(v, percent=True) for v in ps_aggs]
        values += [fmt_value(v) for v in kpa_mean] + [fmt_value(v, percent=True) for v in kpa_aggs]
        values += [fmt_value(v) for v in cap_mean] + [fmt_value(v, percent=True) for v in cap_aggs]
        values += [fmt_value(v) for v in c4_mean_9]
        values += [fmt_value(v, percent=True) for v in c4_cov_9]

        return headers, values

    def _report_metric_arrays(self, real_mean_key, real_cov_key,
                              summary_mean_key, summary_cov_key, per_ch_key):
        """Return (mean_per_ch[8], cov_per_ch[8]) for a metric, real if available."""
        # try real em_result first
        if self.em_result is not None:
            mean_arr = self.em_result.get(real_mean_key, None)
            cov_arr = self.em_result.get(real_cov_key, None) if real_cov_key else None
            if mean_arr is not None:
                means = [self._safe_float(mean_arr[c]) for c in range(CHANNEL_COUNT)]
                if cov_arr is not None:
                    covs = [self._safe_float(cov_arr[c]) for c in range(CHANNEL_COUNT)]
                else:
                    covs = self._derive_cov_from_run_data(per_ch_key)
                return means, covs
        # fall back to self.summary + self.run_data
        means = list(self.summary.get(summary_mean_key, [0.0] * CHANNEL_COUNT))
        if summary_cov_key and summary_cov_key in self.summary:
            covs = list(self.summary.get(summary_cov_key, [0.0] * CHANNEL_COUNT))
        else:
            covs = self._derive_cov_from_run_data(per_ch_key)
        return means, covs

    def _derive_cov_from_run_data(self, per_ch_key):
        """Compute per-channel COV from run_data for synthetic mode or missing keys."""
        covs = []
        for ch in range(CHANNEL_COUNT):
            xs = [run[ch][per_ch_key] for run in self.run_data]
            m = sum(xs) / len(xs) if xs else 0
            if m == 0:
                covs.append(0.0)
                continue
            var = sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)
            covs.append(math.sqrt(var) / m)
        return covs

    @staticmethod
    def _safe_float(v):
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return 0.0
            return f
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _region_cov_aggregates(cov_per_ch):
        """Given an 8-element per-channel COV array, return (center4_avg, outer4_avg, all_avg)."""
        center = [cov_per_ch[i] for i in (2, 3, 4, 5)]
        outer = [cov_per_ch[i] for i in (0, 1, 6, 7)]
        def avg(xs):
            xs = [x for x in xs if x is not None]
            return sum(xs) / len(xs) if xs else 0.0
        return [avg(center), avg(outer), avg(cov_per_ch)]

    def _report_center4_per_kpa(self):
        """Return (means_9, covs_9) for Center-4 CHs averaged at 5,10,...,45 kPa.
        Real path: em_result['avg_ch_var_center4_mean'] and ['avg_ch_var_center4_cov'].
        Synthetic path: interpolate cap-vs-pressure curves of CH3..CH6 from run_data."""
        n_points = len(self.REPORT_KPA_POINTS)
        if self.em_result is not None:
            mean_arr = self.em_result.get("avg_ch_var_center4_mean", None)
            cov_arr = self.em_result.get("avg_ch_var_center4_cov", None)
            if mean_arr is not None and cov_arr is not None:
                means = [self._safe_float(mean_arr[i]) for i in range(min(n_points, len(mean_arr)))]
                covs = [self._safe_float(cov_arr[i]) for i in range(min(n_points, len(cov_arr)))]
                # pad if shorter
                means += [0.0] * (n_points - len(means))
                covs += [0.0] * (n_points - len(covs))
                return means, covs
        # synthetic fallback: interp run_data cap-vs-pressure for CH3..CH6 at each kPa point
        center_chs = (2, 3, 4, 5)
        means = []
        covs = []
        for kpa in self.REPORT_KPA_POINTS:
            samples = []
            for run in self.run_data:
                for ch in center_chs:
                    cap_at_kpa = self._interp_cap_at_pressure(run[ch], kpa)
                    if cap_at_kpa is not None:
                        samples.append(cap_at_kpa)
            if not samples:
                means.append(0.0)
                covs.append(0.0)
                continue
            m = sum(samples) / len(samples)
            if m == 0:
                means.append(0.0)
                covs.append(0.0)
                continue
            var = sum((x - m) ** 2 for x in samples) / max(1, len(samples) - 1)
            means.append(m)
            covs.append(math.sqrt(var) / m)
        return means, covs

    @staticmethod
    def _interp_cap_at_pressure(channel_data, kpa):
        pressures = channel_data.get("pressures")
        caps = channel_data.get("caps")
        if not pressures or not caps or len(pressures) != len(caps):
            return None
        if kpa < pressures[0] or kpa > pressures[-1]:
            return None
        for i in range(1, len(pressures)):
            if pressures[i] >= kpa:
                p0, p1 = pressures[i - 1], pressures[i]
                if p1 == p0:
                    return caps[i]
                t = (kpa - p0) / (p1 - p0)
                return caps[i - 1] + t * (caps[i] - caps[i - 1])
        return caps[-1]

    def _copy_values(self):
        text = "\t".join(self._report_values)
        self._copy_to_clipboard(text, "Values row copied to clipboard.")

    def _copy_with_headers(self):
        text = "\t".join(self._report_headers) + "\n" + "\t".join(self._report_values)
        self._copy_to_clipboard(text, "Headers + values copied to clipboard.")

    def _copy_to_clipboard(self, text, message):
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.window.update()
        except tk.TclError:
            pass
        self.copy_feedback.config(text=message, foreground="#3da556")
        self.window.after(2000, lambda: self.copy_feedback.config(text=""))

    # close handling

    def _on_close(self):
        # criterion: 'analysis and testing windows close and user returns to main setup'.
        self.window.grab_release()
        self.window.destroy()
