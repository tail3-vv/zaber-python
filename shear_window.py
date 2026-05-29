import tkinter as tk
from tkinter import ttk
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
Shear Testing Window: Feature 1.7 (stories 1.7.1 through 1.7.3).
Live Force vs Time graph with start / stop / perform analysis controls.
Preview mode uses a simulated ~1.5 N rise so the gui can be tested 
without real hardware.
"""


def _style_axes_clean(ax, xlabel, ylabel):
    # clean look 
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


STATE_IDLE = "IDLE"
STATE_READY = "READY"
STATE_RUNNING = "RUNNING"
STATE_PAUSED_RESET = "PAUSED_RESET_REQUIRED"
STATE_COMPLETED = "COMPLETED"

CLOSE_BLOCKING_STATES = (STATE_RUNNING, STATE_PAUSED_RESET)

# preview simulation tuning
SAMPLE_INTERVAL_MS = 50
PAUSE_LOCKOUT_MS = 5000
TARGET_FORCE_N = 1.5
APPROACH_TAU_S = 1.8  # exponential approach time constant for the ~1.5 N asymptote


class ShearWindow(tk.Toplevel):

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.title("Shear Testing Window")
        # open just inside the upper-left corner, slightly offset from main_window
        self.geometry("1060x780+0+30")
        self.minsize(840, 560)
        self.configure(bg="#eef2f7")
        self.main_window = main_window
        self.grab_set()

        # state machine
        self.state = STATE_IDLE
        self._sim_after_id = None
        self._pause_after_id = None
        self._sim_started_at = 0.0
        # live samples for the current run (reset on Start, preserved on Stop)
        self.run_samples_x = []
        self.run_samples_y = []
        # latest completed-or-paused samples (used for analysis)
        self.latest_samples_x = []
        self.latest_samples_y = []
        # tracks whether we have any data yet (enables perform analysis)
        self.has_data = False

        # graph display controls (story 1.7.3)
        self.last_seconds = tk.IntVar(value=30)
        self.y_min = tk.DoubleVar(value=0.0)
        self.y_max = tk.DoubleVar(value=5.0)
        self.show_markers = tk.BooleanVar(value=False)
        self.cumulative_time = tk.BooleanVar(value=False)
        # re-render graph when any display setting changes
        for v in (self.last_seconds, self.y_min, self.y_max,
                  self.show_markers, self.cumulative_time):
            v.trace_add("write", self._on_display_setting_changed)

        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)
        self.bind("<Escape>", self._on_escape)

        self._create_widgets()
        self._set_state(STATE_READY)

        # restore main scroll on close
        def on_destroy(event):
            if event.widget is self:
                try:
                    self.main_window.restore_main_mousewheel()
                except Exception:
                    pass
        self.bind("<Destroy>", on_destroy)

    # widget construction
    def _create_widgets(self):
        outer = tk.Frame(self, bg="#eef2f7")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg="#eef2f7", highlightthickness=0, bd=0,
                           yscrollincrement=8)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scroll_frame = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        # scroll_frame height = max(natural content, canvas height) so the body card
        # fills extra vertical space when content < canvas, and scroll kicks in otherwise.
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

        # title
        ttk.Label(container, text="Shear Testing Window",
                  style="Title.TLabel").pack(anchor="w", pady=(0, 12))

        # status pill
        self.status_pill_text = tk.StringVar(value="")
        pill = tk.Frame(container, bg="#e7efff",
                        highlightthickness=1,
                        highlightbackground="#cdd9f0",
                        highlightcolor="#cdd9f0")
        pill.pack(fill="x", pady=(0, 12))
        tk.Label(pill, textvariable=self.status_pill_text,
                 bg="#e7efff", fg="#3856b3",
                 padx=12, pady=8,
                 font=("Helvetica", 10, "bold"),
                 anchor="w", justify="left").pack(fill="x")

        # graph card: title + matplotlib figure + display controls row underneath
        graph_card = tk.Frame(container, bg="#ffffff",
                              highlightthickness=1,
                              highlightbackground="#dde2eb",
                              highlightcolor="#dde2eb")
        graph_card.pack(fill="both", expand=True, pady=(0, 14))
        graph_inner = ttk.Frame(graph_card, padding=(18, 14, 18, 14),
                                style="Card.TFrame")
        graph_inner.pack(fill="both", expand=True)

        ttk.Label(graph_inner, text="Live Force vs Time",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))

        # small initial figsize so the controls + action rows stay visible without scrolling.
        # tkcairo renders vector paths, so the line stays crisp when the widget expands.
        self.fig = Figure(figsize=(5.0, 2.6), dpi=144, facecolor="#ffffff",
                          layout="constrained")
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot([], [], color="#3a5dd9", linewidth=1.6,
                                  antialiased=True, solid_capstyle="round",
                                  solid_joinstyle="round")
        _style_axes_clean(self.ax, "Time Elapsed (seconds)", "Force (N)")
        self._apply_graph_limits()
        self.graph_canvas = _FigureCanvas(self.fig, master=graph_inner)
        self.graph_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.graph_canvas.draw()

        # graph display controls (story 1.7.3)
        # column 0 has minsize so the "Last Seconds to Display" label always fits and
        # the entry below it is never narrower than the label.
        # columns 1-4 share equal width via uniform="ctrl" so the rest line up.
        controls = ttk.Frame(graph_inner, style="Card.TFrame")
        controls.pack(fill="x", pady=(12, 0))
        controls.grid_columnconfigure(0, weight=3, minsize=240)
        for i in range(1, 5):
            controls.grid_columnconfigure(i, weight=1, uniform="ctrl")

        # column 0: last seconds displayed
        ttk.Label(controls, text="Last Seconds to Display",
                  style="FieldLabel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(controls, textvariable=self.last_seconds,
                  style="Input.TEntry", cursor="xterm").grid(
            row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))

        # column 1: y axis min
        ttk.Label(controls, text="Y-Axis Min",
                  style="FieldLabel.TLabel").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Entry(controls, textvariable=self.y_min,
                  style="Input.TEntry", cursor="xterm").grid(
            row=1, column=1, sticky="ew", padx=8, pady=(4, 0))

        # column 2: y axis limit
        ttk.Label(controls, text="Y-Axis Limit",
                  style="FieldLabel.TLabel").grid(row=0, column=2, sticky="w", padx=8)
        ttk.Entry(controls, textvariable=self.y_max,
                  style="Input.TEntry", cursor="xterm").grid(
            row=1, column=2, sticky="ew", padx=8, pady=(4, 0))

        # column 3: show markers checkbox (spans both rows so it centers vertically)
        ttk.Checkbutton(controls, text="Show markers",
                        variable=self.show_markers).grid(
            row=0, column=3, rowspan=2, sticky="w", padx=8)

        # column 4: cumulative time checkbox
        ttk.Checkbutton(controls, text="Cumulative time",
                        variable=self.cumulative_time).grid(
            row=0, column=4, rowspan=2, sticky="w", padx=(8, 0))

        # action row: start / stop / perform analysis (50/33/17 split via expand)
        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(0, 4))
        self.start_btn = ttk.Button(actions, text="▶ Start", command=self.on_start,
                                    style="Green.TButton")
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.stop_btn = ttk.Button(actions, text="⏹ Stop", command=self.on_stop,
                                   style="Outline.TButton")
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.analysis_btn = ttk.Button(actions, text="Perform analysis",
                                       command=self.on_perform_analysis,
                                       style="Outline.TButton")
        self.analysis_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # mousewheel routing while we're shown
        self.main_window.install_mousewheel(canvas)

    # state machine
    def _set_state(self, new_state):
        self.state = new_state
        self._refresh_status_pill()
        self._refresh_button_states()

    def _status_pill_message(self):
        s = self.state
        if s == STATE_IDLE:
            return "shear testing window opened."
        if s == STATE_READY:
            if self.has_data:
                return "ready. click start to record another run, or perform analysis to use the latest run."
            return "ready. click start to begin recording."
        if s == STATE_RUNNING:
            return "running. live shear graph updating."
        if s == STATE_PAUSED_RESET:
            return "stopped. actuator returning home, controls locked for 5s. latest data preserved."
        if s == STATE_COMPLETED:
            return "analysis stopped live plotting. exit enabled."
        return ""

    def _refresh_status_pill(self):
        self.status_pill_text.set(f"{self.state}: {self._status_pill_message()}")

    def _refresh_button_states(self):
        s = self.state
        # start enabled when ready (with or without data); disabled while running, locked, completed
        start_on = s == STATE_READY
        stop_on = s == STATE_RUNNING
        # analysis enabled once data exists and the window is not in the middle of running or locked
        analysis_on = self.has_data and s in (STATE_READY, STATE_COMPLETED)
        self.start_btn.config(state=tk.NORMAL if start_on else tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL if stop_on else tk.DISABLED)
        self.analysis_btn.config(state=tk.NORMAL if analysis_on else tk.DISABLED)

    # button handlers
    def on_start(self):
        if self.state != STATE_READY:
            return
        # restarting after a stop: discard previous live graph; latest_samples are already
        # captured for analysis, so we just reset the active buffer
        self.run_samples_x = []
        self.run_samples_y = []
        self.line.set_data([], [])
        self.graph_canvas.draw_idle()
        self._set_state(STATE_RUNNING)
        self._sim_started_at = datetime.now().timestamp()
        self._schedule_sample()

    def on_stop(self):
        if self.state != STATE_RUNNING:
            return
        if self._sim_after_id is not None:
            self.after_cancel(self._sim_after_id)
            self._sim_after_id = None
        # preserve the latest run for analysis even though the graph resets visually
        self.latest_samples_x = list(self.run_samples_x)
        self.latest_samples_y = list(self.run_samples_y)
        self.has_data = bool(self.latest_samples_x)
        # graph resets (criterion: pause resets graph; latest data preserved)
        self.run_samples_x = []
        self.run_samples_y = []
        self.line.set_data([], [])
        self.graph_canvas.draw_idle()
        self._set_state(STATE_PAUSED_RESET)
        # 5s lockout then back to ready
        self._pause_after_id = self.after(PAUSE_LOCKOUT_MS, self._after_pause_lockout)

    def _after_pause_lockout(self):
        self._pause_after_id = None
        self._set_state(STATE_READY)

    def on_perform_analysis(self):
        if not self.has_data or self.state not in (STATE_READY, STATE_COMPLETED):
            return
        # stop any live plotting (acts as Stop, criterion)
        if self._sim_after_id is not None:
            self.after_cancel(self._sim_after_id)
            self._sim_after_id = None
        self._set_state(STATE_COMPLETED)
        try:
            self.main_window.perform_analysis()
        except Exception:
            pass
        self.grab_release()
        self.destroy()

    # simulation loop for preview mode
    # TODO: MAKE THIS NOT SIMULATED
    def _schedule_sample(self):
        if self.state != STATE_RUNNING:
            return
        elapsed = datetime.now().timestamp() - self._sim_started_at
        force = self._simulated_force(elapsed)
        self.run_samples_x.append(elapsed)
        self.run_samples_y.append(force)
        # mirror into latest_samples so analysis source is always current
        self.latest_samples_x = list(self.run_samples_x)
        self.latest_samples_y = list(self.run_samples_y)
        self.has_data = True
        self._redraw_graph()
        self._sim_after_id = self.after(SAMPLE_INTERVAL_MS, self._schedule_sample)

    # TODO: MAKE THIS NOT SIMULATED
    def _simulated_force(self, t):
        # exponential approach to TARGET_FORCE_N (~1.5 N) per criterion
        if t <= 0:
            return 0.0
        return TARGET_FORCE_N * (1.0 - math.exp(-t / APPROACH_TAU_S))

    # graph rendering
    def _apply_graph_limits(self):
        try:
            ymin = float(self.y_min.get())
            ymax = float(self.y_max.get())
        except (tk.TclError, ValueError):
            ymin, ymax = 0.0, 5.0
        if ymax <= ymin:
            ymax = ymin + 1.0
        self.ax.set_ylim(ymin, ymax)

    def _redraw_graph(self):
        # marker style
        if self.show_markers.get():
            self.line.set_marker("o")
            self.line.set_markersize(3)
        else:
            self.line.set_marker("")

        self.line.set_data(self.run_samples_x, self.run_samples_y)

        # apply y limits live
        try:
            ymin = float(self.y_min.get())
            ymax = float(self.y_max.get())
            if ymax > ymin:
                self.ax.set_ylim(ymin, ymax)
        except (tk.TclError, ValueError):
            pass

        # x window: cumulative shows all, otherwise show the last N seconds
        if self.cumulative_time.get():
            if self.run_samples_x:
                self.ax.set_xlim(0, max(self.run_samples_x[-1], 1.0))
            else:
                self.ax.set_xlim(0, 1.0)
        else:
            try:
                window = max(1, int(self.last_seconds.get()))
            except (tk.TclError, ValueError):
                window = 30
            if self.run_samples_x and self.run_samples_x[-1] > window:
                self.ax.set_xlim(self.run_samples_x[-1] - window, self.run_samples_x[-1])
            else:
                self.ax.set_xlim(0, window)

        self.graph_canvas.draw_idle()

    def _on_display_setting_changed(self, *_args):
        try:
            self._redraw_graph()
        except Exception:
            pass

    # close handling
    def _on_close_attempt(self):
        if self.state in CLOSE_BLOCKING_STATES:
            return
        self.grab_release()
        self.destroy()

    def _on_escape(self, _event):
        if self.state in CLOSE_BLOCKING_STATES:
            return "break"
        self._on_close_attempt()
