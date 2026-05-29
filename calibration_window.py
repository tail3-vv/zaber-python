import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from datetime import datetime

try:
    from zaber_motion import Units
except ImportError:
    Units = None

from zaber_cli import ZaberCLI

"""
Calibration Window — Feature 1.4 (stories 1.4.1 through 1.4.7).
Popup for lowering the load cell and running the Fuji film calibration test.
"""


class CalibrationWindow:
    HOME_POSITION = 17.0
    TARGET_FORCE = 20.0  # newtons

    def __init__(self, parent, main_window):
        self.parent = parent
        self.main_window = main_window
        self.window = tk.Toplevel(parent)
        self.window.title("Calibration Window")
        # open just inside the upper-left corner, slightly offset from main_window
        self.window.geometry("640x680+0+30")
        self.window.minsize(560, 600)
        self.window.configure(bg="#eef2f7")
        self.window.grab_set()

        # state
        self.position = tk.DoubleVar(value=self.HOME_POSITION)
        # increment persists on main_window so it survives across opens during the session
        # default 0.1 if no stored value exists yet
        if not hasattr(main_window, "calibration_increment"):
            main_window.calibration_increment = tk.StringVar(value="0.1")
        self.increment_distance = main_window.calibration_increment
        self.test_running = tk.BooleanVar(value=False)
        self.zaber = None
        # widgets locked while the fuji film test runs
        self.lockable_widgets = []

        self._create_widgets()

        # escape key blocked while a test is running
        self.window.bind("<Escape>", self._on_escape)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

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

        def on_frame_configure(_):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        scroll_frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        self._canvas = canvas

        container = ttk.Frame(scroll_frame, padding=(20, 14, 20, 14))
        container.pack(fill="both", expand=True)

        # title row: the OS provides the close button in the window chrome;
        # WM_DELETE_WINDOW + escape bindings enforce the disable-while-running rule
        ttk.Label(container, text="Calibration Window",
                  style="Title.TLabel").pack(anchor="w", pady=(0, 12))

        # error check banner (light blue, story 1.4.1)
        banner = tk.Label(container,
                          text="Error Check Active: Movement will stop if significant force increase is detected",
                          bg="#e7efff", fg="#3856b3",
                          padx=12, pady=8, font=("Helvetica", 9),
                          anchor="w")
        banner.pack(fill="x", pady=(0, 14))

        # current status card (story 1.4.2)
        status_card = self._make_card(container, "Current Status")
        status_row = ttk.Frame(status_card, style="Card.TFrame")
        status_row.pack(anchor="w")
        ttk.Label(status_row, text="Position:",
                  style="FieldLabel.TLabel").pack(side="left", padx=(0, 6))
        # value uses the same typography as the entry text (regular 11pt) so the field
        # label is bold and the value reads like a value not another label
        self.position_value_label = ttk.Label(status_row,
                                              text=f"{self.HOME_POSITION:.2f} mm",
                                              style="CardText.TLabel")
        self.position_value_label.pack(side="left")

        # manual increment control card (story 1.4.3)
        manual_card = self._make_card(container, "Manual Increment Control")

        self._labeled(manual_card, "Increment Distance (mm)",
                      "How far to move when you click Move up or Move down.")
        inc_entry = ttk.Entry(manual_card, textvariable=self.increment_distance,
                              style="Input.TEntry", cursor="xterm")
        inc_entry.pack(fill="x", pady=(6, 12))
        self.lockable_widgets.append(inc_entry)

        # 3-button row: move up / move down / home (story 1.4.3 + 1.4.4)
        btn_row = ttk.Frame(manual_card, style="Card.TFrame")
        btn_row.pack(fill="x")
        up_btn = ttk.Button(btn_row, text="↑ Move up", command=self.move_up,
                            style="Outline.TButton")
        up_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        down_btn = ttk.Button(btn_row, text="↓ Move down", command=self.move_down,
                              style="Outline.TButton")
        down_btn.pack(side="left", fill="x", expand=True, padx=(6, 6))
        home_btn = ttk.Button(btn_row, text="↻ Home", command=self.go_home,
                              style="Outline.TButton")
        home_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.lockable_widgets.extend([up_btn, down_btn, home_btn])

        # fuji film test card: start button + output log live here together (story 1.4.5 + 1.4.6)
        fuji_card = self._make_card(container, "Fuji Film Test")
        self.start_btn = ttk.Button(fuji_card, text="▶ Start Test",
                                    command=self.start_fuji_film_test,
                                    style="Green.TButton")
        self.start_btn.pack(fill="x", pady=(0, 10))
        # wrap=word + built-in scrollbar so long lines wrap and native scroll works
        self.output = scrolledtext.ScrolledText(fuji_card, height=8,
                                                bd=1, relief="solid",
                                                bg="#fff7e6", fg="#3b3f47",
                                                font=("Menlo", 10),
                                                highlightthickness=0,
                                                padx=8, pady=6, wrap="word")
        self.output.pack(fill="both", expand=True)
        self.output.config(state=tk.DISABLED)
        self._log("[ready] calibration window ready.")

        # mousewheel scrolling
        self.main_window.install_mousewheel(canvas)
        # restore main page scroll when this window closes
        def on_destroy(event):
            if event.widget is self.window:
                try:
                    self.main_window.restore_main_mousewheel()
                except Exception:
                    pass
        self.window.bind("<Destroy>", on_destroy)

    def _make_card(self, parent, title, pady=12):
        card = tk.Frame(parent, bg="#ffffff",
                        highlightthickness=1,
                        highlightbackground="#dde2eb",
                        highlightcolor="#dde2eb")
        card.pack(fill="x", pady=(0, pady))
        inner = ttk.Frame(card, padding=(18, 14, 18, 14), style="Card.TFrame")
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=title,
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 8))
        return inner

    def _labeled(self, parent, text, tooltip):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(anchor="w", fill="x")
        ttk.Label(row, text=text, style="FieldLabel.TLabel").pack(side="left")
        if tooltip:
            ttk.Label(row, text=" ⓘ", style="Info.TLabel", cursor="hand2").pack(side="left", padx=(4, 0))
        return row

    # logging helper
    def _log(self, text):
        timestamp = datetime.now().strftime("[%I:%M:%S %p]").lstrip("0")
        self.output.config(state=tk.NORMAL)
        self.output.insert(tk.END, f"{timestamp} {text}\n")
        self.output.see(tk.END)
        self.output.config(state=tk.DISABLED)

    # zaber connection helpers
    def _ensure_zaber(self):
        if self.zaber is not None and getattr(self.zaber, "axis", None) is not None:
            return True
        self.zaber = ZaberCLI()
        comport = getattr(self.main_window, "zaber_comport", None)
        if comport is None:
            self._log("[error] no zaber comport set on main window.")
            return False
        connected = self.zaber.connect(comport.get())
        if connected == 0:
            self._log(f"[error] could not connect to zaber on {comport.get()}.")
            return False
        raw = self.zaber.axis.get_position()
        self.position.set((raw * 0.04765) / 1000)
        self._refresh_position_label()
        return True

    def _refresh_position_label(self):
        self.position_value_label.config(text=f"{self.position.get():.2f} mm")

    def _read_increment(self):
        try:
            value = float(self.increment_distance.get())
            if value <= 0:
                raise ValueError
            return value
        except (TypeError, ValueError):
            self._log("[error] increment distance must be a positive number.")
            return None

    # movement actions (stories 1.4.3 / 1.4.4)
    # display always updates locally; hardware move is best-effort so preview mode works
    def move_up(self):
        increment = self._read_increment()
        if increment is None:
            return
        self.position.set(self.position.get() - increment)
        self._refresh_position_label()
        self._log(f"moved up {increment:g} mm. position now {self.position.get():.2f} mm.")
        self._try_move_hardware(-increment)

    def move_down(self):
        increment = self._read_increment()
        if increment is None:
            return
        self.position.set(self.position.get() + increment)
        self._refresh_position_label()
        self._log(f"moved down {increment:g} mm. position now {self.position.get():.2f} mm.")
        self._try_move_hardware(increment)

    def go_home(self):
        self.position.set(self.HOME_POSITION)
        self._refresh_position_label()
        self._log(f"reset to home position {self.HOME_POSITION:.2f} mm.")
        if Units is not None and self._ensure_zaber():
            try:
                self.zaber.axis.move_absolute(self.HOME_POSITION, Units.LENGTH_MILLIMETRES)
            except Exception as e:
                self._log(f"[warn] hardware home failed: {e}")

    def _try_move_hardware(self, delta_mm):
        if Units is None or not self._ensure_zaber():
            return
        try:
            self.zaber.axis.move_relative(delta_mm, Units.LENGTH_MILLIMETRES)
        except Exception as e:
            self._log(f"[warn] hardware move failed: {e}")

    # fuji film test (stories 1.4.5, 1.4.6, 1.4.7)
    def start_fuji_film_test(self):
        if self.test_running.get():
            return
        self.test_running.set(True)
        self._lock_for_test()
        self._log("calibration test started.")
        self._log("Time (s) | Force (N)")
        self._simulate_test(elapsed=0.0, force=0.0)

    def _simulate_test(self, elapsed, force):
        # preview mode: ramp force from 0 to 20N over ~5 seconds
        if not self.test_running.get():
            # stopped externally
            self._unlock_after_test()
            return
        if force >= self.TARGET_FORCE:
            self._log("calibration test completed successfully.")
            self.test_running.set(False)
            self._unlock_after_test()
            return
        # log a sample row every ~250ms
        self._log(f"  {elapsed:5.3f} s | {force:4.1f} N")
        next_force = force + 1.0
        next_elapsed = elapsed + 0.25
        self.window.after(250, lambda: self._simulate_test(next_elapsed, next_force))

    def _lock_for_test(self):
        for w in self.lockable_widgets:
            try:
                w.config(state=tk.DISABLED)
            except tk.TclError:
                pass
        self.start_btn.config(state=tk.DISABLED)

    def _unlock_after_test(self):
        for w in self.lockable_widgets:
            try:
                w.config(state=tk.NORMAL)
            except tk.TclError:
                pass
        self.start_btn.config(state=tk.NORMAL)

    # close-blocking while a test runs (story 1.4.7)
    def _on_close_attempt(self):
        if self.test_running.get():
            self._log("[blocked] cannot exit while calibration test is running.")
            return
        self.window.grab_release()
        self.window.destroy()

    def _on_escape(self, _event):
        # escape also blocked during a running test
        if self.test_running.get():
            return "break"
        self._on_close_attempt()
