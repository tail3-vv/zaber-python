import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from datetime import datetime
import math

import matplotlib
# tkcairo (vector-quality rendering via pycairo) with tkagg as fallback
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
matplotlib.rcParams["savefig.dpi"] = 200
from matplotlib.figure import Figure

"""
EM Testing Window — Feature 1.5 (stories 1.5.1 through 1.5.6).
Opens when the user clicks Begin Test with Test Type = EM Test.
State machine drives status pill, log, button enablement, and close behavior.
"""


def _style_axes_clean(ax, xlabel, ylabel):
    # clean axis style
    ax.set_xlabel(xlabel, fontsize=9.5, color="#3b3f47", labelpad=4)
    ax.set_ylabel(ylabel, fontsize=9.5, color="#3b3f47", labelpad=4)
    ax.tick_params(colors="#5a6473", labelsize=8.5, length=4, width=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cdd3de")
    ax.spines["bottom"].set_color("#cdd3de")
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.grid(True, which="major", color="#e8ecf2", linewidth=0.7)
    ax.grid(True, which="minor", color="#f3f5fa", linewidth=0.5)
    ax.minorticks_on()
    ax.set_axisbelow(True)


# state machine constants
STATE_IDLE = "IDLE"
STATE_READY = "READY"
STATE_CONNECTING = "CONNECTING"
STATE_RUNNING = "RUNNING"
STATE_PAUSED_RESET = "PAUSED_RESET_REQUIRED"
STATE_BETWEEN_RUNS = "BETWEEN_RUNS_PAUSED"
STATE_COMPLETED = "COMPLETED"
STATE_ERROR = "ERROR"

# while these states are active, the os close button is blocked
CLOSE_BLOCKING_STATES = (STATE_RUNNING, STATE_CONNECTING, STATE_PAUSED_RESET)

# simulation tuning
RUN_DURATION_S = 5.0
SAMPLE_INTERVAL_MS = 50
PAUSE_LOCKOUT_MS = 5000
# force ramp: smooth S-curve toward ~18 N over RUN_DURATION_S
PEAK_FORCE_N = 18.0


class EMTestWindow:

    def __init__(self, parent, main_window):
        self.parent = parent
        self.main_window = main_window

        self.window = tk.Toplevel(parent)
        self.window.title("EM Testing Window")
        self.window.geometry("1180x780+0+30")
        self.window.minsize(880, 560)
        self.window.configure(bg="#eef2f7")
        self.window.grab_set()

        # state
        self.state = STATE_IDLE
        try:
            self.total_runs = int(main_window.n_runs.get())
        except (tk.TclError, ValueError):
            self.total_runs = 3
        if self.total_runs < 1:
            self.total_runs = 1
        # in redo mode: only the selected run is repeated (count = 1)
        if main_window.redo_mode.get():
            self.total_runs = 1
        self.current_run = 1
        # samples for the live graph (reset every run)
        self.run_samples_x = []
        self.run_samples_y = []
        # simulation control
        self._sim_after_id = None
        self._pause_after_id = None
        self._sim_started_at = 0.0
        # close protocol + escape
        self.window.protocol("WM_DELETE_WINDOW", self._on_close_attempt)
        self.window.bind("<Escape>", self._on_escape)

        self._create_widgets()

        # the room starts at READY waiting for the user to press Start
        self._set_state(STATE_READY)

        # restore main page scroll when this window closes
        def on_destroy(event):
            if event.widget is self.window:
                try:
                    self.main_window.restore_main_mousewheel()
                except Exception:
                    pass
                self._reset_redo_state_on_close()
        self.window.bind("<Destroy>", on_destroy)

    # widget construction
    def _create_widgets(self):
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

        # scroll_frame height = max(natural content, canvas height).
        # content > canvas: scroll_frame extends naturally, scrolling kicks in.
        # content < canvas: scroll_frame fills canvas, body card expands to fill
        # the extra vertical space
        def _reconfigure():
            scroll_frame.update_idletasks()
            canvas_h = canvas.winfo_height() or 1
            natural_h = scroll_frame.winfo_reqheight()
            h = max(natural_h, canvas_h)
            current_h = int(canvas.itemcget(window_id, "height") or "0")
            if h != current_h:
                canvas.itemconfig(window_id, height=h)
            canvas.configure(scrollregion=canvas.bbox("all"))
        def schedule_reconfigure(_=None):
            canvas.after_idle(_reconfigure)
        scroll_frame.bind("<Configure>", schedule_reconfigure)
        def on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
            schedule_reconfigure()
        canvas.bind("<Configure>", on_canvas_configure)
        self._canvas = canvas

        container = ttk.Frame(scroll_frame, padding=(20, 14, 20, 14))
        container.pack(fill="both", expand=True)

        # title row
        ttk.Label(container, text="EM Testing Window",
                  style="Title.TLabel").pack(anchor="w", pady=(0, 12))

        # status pill: updates per state
        self.status_pill_text = tk.StringVar(value="")
        self.status_pill_frame = tk.Frame(container, bg="#e7efff",
                                          highlightthickness=1,
                                          highlightbackground="#cdd9f0",
                                          highlightcolor="#cdd9f0")
        self.status_pill_frame.pack(fill="x", pady=(0, 12))
        self.status_pill_label = tk.Label(self.status_pill_frame,
                                          textvariable=self.status_pill_text,
                                          bg="#e7efff", fg="#3856b3",
                                          padx=12, pady=8,
                                          font=("Helvetica", 10, "bold"),
                                          anchor="w", justify="left")
        self.status_pill_label.pack(fill="x")

        # info banner (story 1.5.x)
        banner = tk.Label(container,
                          text="EM testing will automatically pause between runs.",
                          bg="#f4f7fc", fg="#3b3f47",
                          padx=12, pady=6, font=("Helvetica", 9),
                          anchor="w")
        banner.pack(fill="x", pady=(0, 14))

        # two-column card: status log on left, force graph on right
        body_card = tk.Frame(container, bg="#ffffff",
                             highlightthickness=1,
                             highlightbackground="#dde2eb",
                             highlightcolor="#dde2eb")
        body_card.pack(fill="both", expand=True, pady=(0, 14))

        body_inner = ttk.Frame(body_card, padding=(18, 14, 18, 14),
                               style="Card.TFrame")
        body_inner.pack(fill="both", expand=True)

        two_col = ttk.Frame(body_inner, style="Card.TFrame")
        two_col.pack(fill="both", expand=True)
        two_col.grid_columnconfigure(0, weight=1, uniform="em")
        two_col.grid_columnconfigure(1, weight=1, uniform="em")
        two_col.grid_rowconfigure(0, weight=1)

        # left: current em test status (story 1.5.2)
        left_col = ttk.Frame(two_col, style="Card.TFrame")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(left_col, text="Current EM Test Status",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
        # same cream + built-in scrollbar pattern as the fuji film output box
        self.log = scrolledtext.ScrolledText(left_col, height=10,
                                             bd=1, relief="solid",
                                             bg="#fff7e6", fg="#3b3f47",
                                             font=("Menlo", 10),
                                             highlightthickness=0,
                                             padx=8, pady=6, wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.config(state=tk.DISABLED)

        # right: live force vs time graph (story 1.5.5)
        right_col = ttk.Frame(two_col, style="Card.TFrame")
        right_col.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right_col, text="Live Force vs Time",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

        self.fig = Figure(figsize=(3.6, 2.4), dpi=144, facecolor="#ffffff",
                          layout="constrained")
        self.ax = self.fig.add_subplot(111)
        self._style_axes()
        self.line, = self.ax.plot([], [], color="#3a5dd9", linewidth=1.6,
                                  antialiased=True, solid_capstyle="round",
                                  solid_joinstyle="round",
                                  label=f"Run {self.current_run}")
        self.ax.legend(loc="upper left", fontsize=8.5, frameon=False)

        self.graph_canvas = _FigureCanvas(self.fig, master=right_col)
        self.graph_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.graph_canvas.draw()

        # bottom action row: start / pause / perform analysis
        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(0, 4))
        self.start_btn = ttk.Button(actions, text="▶ Start", command=self.on_start,
                                    style="Green.TButton")
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.pause_btn = ttk.Button(actions, text="⏸ Pause", command=self.on_pause,
                                    style="Outline.TButton")
        self.pause_btn.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.analysis_btn = ttk.Button(actions, text="Perform analysis",
                                       command=self.on_perform_analysis,
                                       style="Outline.TButton")
        self.analysis_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # mousewheel scrolling
        self.main_window.install_mousewheel(canvas)

        # initial log header
        self._log_status(f"em testing window opened. {self.total_runs} run(s) configured.")
        self._log_table_header()

    def _style_axes(self):
        self.ax.set_xlim(0, RUN_DURATION_S)
        self.ax.set_ylim(0, PEAK_FORCE_N * 1.15)
        _style_axes_clean(self.ax, "Time (s)", "Force (N)")

    # state machine
    def _set_state(self, new_state):
        self.state = new_state
        self._refresh_status_pill()
        self._refresh_button_states()

    def _refresh_status_pill(self):
        msg = self._status_pill_message()
        self.status_pill_text.set(f"{self.state}: {msg}")

    def _status_pill_message(self):
        s = self.state
        if s == STATE_IDLE:
            return "em testing window opened."
        if s == STATE_READY:
            return f"click start to begin run {self.current_run}."
        if s == STATE_CONNECTING:
            return "connecting to hardware..."
        if s == STATE_RUNNING:
            return f"run {self.current_run} running."
        if s == STATE_PAUSED_RESET:
            return f"run {self.current_run} paused. actuator returning home, controls locked for 5s."
        if s == STATE_BETWEEN_RUNS:
            return (f"run {self.current_run - 1} completed. "
                    f"click start before run {self.current_run}.")
        if s == STATE_COMPLETED:
            return f"all {self.total_runs} run(s) completed. perform analysis is now available."
        if s == STATE_ERROR:
            return "an error occurred. close the window and try again."
        return ""

    def _refresh_button_states(self):
        s = self.state
        # start enabled when ready / between runs; disabled while running / locked / completed
        start_on = s in (STATE_READY, STATE_BETWEEN_RUNS)
        # pause enabled only while a run is actually progressing
        pause_on = s == STATE_RUNNING
        # analysis enabled only when all runs done
        analysis_on = s == STATE_COMPLETED
        self.start_btn.config(state=tk.NORMAL if start_on else tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL if pause_on else tk.DISABLED)
        self.analysis_btn.config(state=tk.NORMAL if analysis_on else tk.DISABLED)

    # status log
    def _log_status(self, message):
        ts = datetime.now().strftime("[%I:%M:%S %p]").lstrip("0")
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, f"{ts} {self.state}: {message}\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _log_table_header(self):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, "Run Number | Time (s) | Force (N)\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _log_force_row(self, elapsed, force):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END,
                        f"Run {self.current_run:<2} | {elapsed:5.3f} s | {force:5.3f} N\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    # button handlers
    def on_start(self):
        if self.state not in (STATE_READY, STATE_BETWEEN_RUNS):
            return
        self._set_state(STATE_RUNNING)
        self._log_status(f"run {self.current_run} started.")
        self._reset_graph_for_run()
        self._sim_started_at = datetime.now().timestamp()
        self._schedule_sample()

    def on_pause(self):
        if self.state != STATE_RUNNING:
            return
        # cancel any pending sample tick
        if self._sim_after_id is not None:
            self.window.after_cancel(self._sim_after_id)
            self._sim_after_id = None
        self._set_state(STATE_PAUSED_RESET)
        self._log_status(f"run {self.current_run} paused. actuator returning home (5s lockout).")
        # TODO: remove this simulation
        # 5s lockout, then unlock back to ready for the SAME run (run marked incomplete)
        self._pause_after_id = self.window.after(PAUSE_LOCKOUT_MS, self._after_pause_lockout)

    def _after_pause_lockout(self):
        self._pause_after_id = None
        self._log_status(f"lockout complete. ready to retry run {self.current_run}.")
        self._set_state(STATE_READY)

    def on_perform_analysis(self):
        if self.state != STATE_COMPLETED:
            return
        self._log_status("perform analysis clicked.")
        try:
            from em_analysis_window import EMAnalysisWindow
            EMAnalysisWindow(
                self.parent,
                self.main_window,
                target_folder=getattr(self.main_window, "pending_target_path", None),
                runs=self.total_runs,
                sensor_id=self.main_window.sensor_id.get(),
                sensor_type=self.main_window.sensor_type.get(),
            )
        except Exception as exc:
            self._log_status(f"analysis failed: {exc}")
            return
        # close the testing window per criterion 'Close returns to setup' —
        # the analysis window is now the active surface.
        self.window.grab_release()
        self.window.destroy()

    # simulation loop
    # TODO: replace simulation with real stuff
    def _schedule_sample(self):
        if self.state != STATE_RUNNING:
            return
        elapsed = datetime.now().timestamp() - self._sim_started_at
        if elapsed >= RUN_DURATION_S:
            self._on_run_finished()
            return
        force = self._simulated_force(elapsed)
        self.run_samples_x.append(elapsed)
        self.run_samples_y.append(force)
        self._log_force_row(elapsed, force)
        self._redraw_graph()
        self._sim_after_id = self.window.after(SAMPLE_INTERVAL_MS, self._schedule_sample)

    def _simulated_force(self, t):
        # s-curve ramp to PEAK_FORCE_N at t = RUN_DURATION_S
        if t <= 0:
            return 0.0
        norm = max(0.0, min(1.0, t / RUN_DURATION_S))
        return PEAK_FORCE_N * (0.5 - 0.5 * math.cos(math.pi * norm))

    def _reset_graph_for_run(self):
        self.run_samples_x = []
        self.run_samples_y = []
        self.line.set_data([], [])
        self.line.set_label(f"Run {self.current_run}")
        self.ax.legend(loc="upper left", fontsize=8, frameon=False)
        self.graph_canvas.draw_idle()

    def _redraw_graph(self):
        self.line.set_data(self.run_samples_x, self.run_samples_y)
        self.graph_canvas.draw_idle()

    def _on_run_finished(self):
        self._log_status(f"run {self.current_run} completed.")
        self._save_preview_run_files()
        if self.current_run >= self.total_runs:
            self._set_state(STATE_COMPLETED)
            self._log_status(f"all {self.total_runs} run(s) completed.")
        else:
            self.current_run += 1
            self._set_state(STATE_BETWEEN_RUNS)

    # preview-mode file writes (adapted from web_preview/run_web_gui.py)
    # FUT format: xlsx with Index | Load Cell | Time columns
    # CAP format: csv with 16 columns; em_analysis reads cols 0 (Time) and 5-12 (CH1-8)
    def _save_preview_run_files(self):
        target = getattr(self.main_window, "pending_target_path", None)
        if target is None:
            return
        try:
            from pathlib import Path
            target = target if hasattr(target, "exists") else Path(str(target))
            fut_dir = target / "FUT"
            cap_dir = target / "CAP"
            fut_dir.mkdir(parents=True, exist_ok=True)
            cap_dir.mkdir(parents=True, exist_ok=True)
            self._write_preview_fut(fut_dir / f"Run {self.current_run}.xlsx",
                                    self.current_run)
            self._write_preview_cap(cap_dir / f"Run {self.current_run}.csv",
                                    self.current_run)
            self._log_status(f"[preview] saved Run {self.current_run} FUT+CAP files.")
        except Exception as exc:
            self._log_status(f"[warn] could not write preview run files: {exc}")

    # force ramps to ~28 N over 10 s so pressure crosses em_analysis's
    # end_force = 45 kPa with headroom (SA = 325e-6 m^2 → 45 kPa ≈ 14.6 N).
    def _preview_force(self, time_value):
        return max(0.0, 0.5 + time_value * 2.5 + math.log1p(time_value) * 1.0)

    # logistic cap response tuned so em_analysis's find_peaks(prominence=0.08,
    # width=300) detects the inflection peak on every channel:
    # - inflection_force in 6.4..9.2 N (≈20..28 kPa) centers the peak in the
    #   analysed pressure window, leaving ~10 kPa on each side for find_peaks
    #   to measure the descending edges
    # - width=1.8 N → peak slope ≈ 0.20 pF/kPa (well above the 0.08 prominence
    #   threshold) and below the 1.0 derivative-clip threshold
    # - plateau=4.5 keeps every channel under the 10 pF shorted-channel cutoff
    def _preview_cap_delta(self, force, channel):
        inflection_force = 5.0 + channel * 0.4
        width = 1.8
        plateau = 4.5
        return plateau / (1.0 + math.exp(-(force - inflection_force) / width))

    # 1001 samples × 0.01s = 10 seconds of data so that after em_analysis's
    # `[:peak_idx][:-500]` trim there are still enough samples (~1500 at 200Hz)
    # to cover the >= 45 kPa region needed by _derive_and_plot.
    PREVIEW_SAMPLE_COUNT = 1001

    def _write_preview_fut(self, path, run_number):
        import xlsxwriter
        sample_count = self.PREVIEW_SAMPLE_COUNT
        workbook = xlsxwriter.Workbook(str(path))
        worksheet = workbook.add_worksheet(str(run_number))
        worksheet.write("A1", "Index")
        worksheet.write("B1", "Load Cell")
        worksheet.write("C1", "Time")
        for index in range(sample_count):
            time_value = round(index * 0.01, 4)
            force = self._preview_force(time_value)
            worksheet.write(index + 1, 0, index + 1)
            worksheet.write(index + 1, 1, force)
            worksheet.write(index + 1, 2, time_value)
        workbook.close()

    def _write_preview_cap(self, path, run_number):
        import csv
        sample_count = self.PREVIEW_SAMPLE_COUNT
        # 16 columns total: Time, 4 unused, CH1-8 (cols 5-12), 3 trailing unused.
        # Cap scaling kept low enough that delta_cap stays under em_analysis's
        # 10 pF shorted-channel threshold for all 8 channels in the clean preview.
        header = ["Time", "U1", "U2", "U3", "U4",
                  "CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8",
                  "T1", "T2", "T3"]
        with open(str(path), "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for index in range(sample_count):
                time_value = round(index * 0.01, 4)
                force = self._preview_force(time_value)
                channels = []
                for channel in range(1, 9):
                    cap = (18.0
                           + self._preview_cap_delta(force, channel)
                           + math.sin(time_value + channel) * 0.03)
                    channels.append(round(cap, 5))
                row = [time_value, "", "", "", ""] + channels + ["", "", ""]
                writer.writerow(row)

    # close handling
    def _on_close_attempt(self):
        if self.state in CLOSE_BLOCKING_STATES:
            self._log_status("[blocked] cannot exit during a run or lockout.")
            return
        self.window.grab_release()
        self.window.destroy()

    def _on_escape(self, _event):
        if self.state in CLOSE_BLOCKING_STATES:
            return "break"
        self._on_close_attempt()

    def _reset_redo_state_on_close(self):
        # redo workflow reset (criterion): on close, clear redo mode and restore defaults
        try:
            mw = self.main_window
            if mw.redo_mode.get():
                mw.redo_mode.set(False)
                mw.test_type.set("EM Test")
                mw.n_runs.set(3)
                mw.run_to_redo.set("")
                mw._on_test_type_changed()
        except Exception:
            pass
