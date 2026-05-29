import re
import tkinter as tk
from tkinter import Tk
from tkinter import ttk
from tkinter import filedialog as fd
from tkinter import messagebox
from tkinter import scrolledtext
import numpy as np
from time import sleep
import xlsxwriter
from pathlib import Path
from datetime import datetime
from zaber_cli import ZaberCLI
#from futek_cli import FUTEKDeviceCLI
from zaber_motion import Units
#from shear_window import ShearWindow
from control_window import ControlWindow
from em_analysis import EMAnalysis
#from shear_analysis import ShearAnalysis

SENSOR_ID_PATTERN = re.compile(r'^\d{6}B\d{2}S\d{2}(A|B|AB|BA)$', re.IGNORECASE)

"""
File where mainloop is executed.
Holds infrastructure to execute all tests
Implementation for EM testing is here, shear testing implementation is in shear_window
EM testing requires too many dependent variables to be kept in a separate file
"""
class MainWindow:
    def __init__(self):
        self.root = Tk(screenName=None, baseName=None, className='Tk', useTk=1)
        self.root.title("Zaber Stage Testing Setup")
        self.root.geometry("780x505+0+0")
        self.root.minsize(560, 480)
        self.root.configure(bg="#eef2f7")

        # basic settings vars
        self.saved_path = tk.StringVar(value="/Users/jacqueline/Google Drive")
        self.sensor_id = tk.StringVar()
        self.sensor_type = tk.StringVar(value="Standard")

        # sensor id segments start empty
        now = datetime.now()
        self.sensor_year = tk.StringVar(value="")
        self.sensor_month = tk.StringVar(value="")
        self.sensor_day = tk.StringVar(value="")
        self.sensor_batch = tk.StringVar(value="")
        self.sensor_number = tk.StringVar(value="")
        self.sensor_location = tk.StringVar(value="")
        self.sensor_placeholders = {
            "year":  str(now.year)[2:],
            "month": str(now.month).zfill(2),
            "day":   str(now.day).zfill(2),
            "batch": "01",
            "sensor": "01",
            "location": "A",
        }
        self.use_custom_sensor_id = tk.BooleanVar(value=False)
        self.custom_sensor_id = tk.StringVar()

        # test configuration vars
        self.is_create_files = tk.BooleanVar(value=1)
        self.is_pause_between_runs = tk.BooleanVar(value=1)
        self.is_test_started = tk.BooleanVar(value=0)
        self.n_runs = tk.IntVar(value=3)
        self.current_run = tk.IntVar(value=1)
        self.zaber_comport = tk.StringVar(value="COM3")
        self.test_type = tk.StringVar(value="EM Test")
        self.surface_area = tk.StringVar(value="325")

        # verify / redo / existing test state
        self.settings_verified = tk.BooleanVar(value=False)
        self.redo_mode = tk.BooleanVar(value=False)
        self.run_to_redo = tk.StringVar(value="")
        self.existing_test_action = tk.StringVar(value="")  # "", "versioned", "overwrite", "redo"
        # path picked at begin test; folders only get created when perform analysis runs
        self.pending_target_path = None
        self.folder_banner_text = tk.StringVar(value="")
        self.changed_banner_text = tk.StringVar(value="")

        # test execution state
        self.textbox = None
        self.pause_btn = None  # kept as hidden widget for compatibility with existing logic
        self.sensor_preview_lbl = None
        self.custom_sensor_entry = None
        self.sensor_segment_entries = []
        self.toggle_pause = tk.BooleanVar(value=0)
        self.is_warning_cancel = tk.BooleanVar(value=0)
        self.widgets = []

        # test config card refs (built after verify)
        self.test_config_card = None
        self.folder_banner_lbl = None
        self.changed_banner_frame = None
        self.test_config_widgets = {}  # name -> widget for enable/disable rules

        # sensor id widget refs
        self.sensor_builder_frame = None  # the unified id box
        self.sensor_preview_row = None  # holder for sensor_preview_lbl, hidden in custom mode

        # sync sensor_id with builder segments + custom entry.
        for var in (self.sensor_year, self.sensor_month, self.sensor_day,
                    self.sensor_batch, self.sensor_number, self.sensor_location,
                    self.custom_sensor_id):
            var.trace_add('write', self._update_sensor_id)
        self.use_custom_sensor_id.trace_add('write', self._update_sensor_id)

        # reverification: any basic settings change after verify invalidates the verification
        for var in (self.saved_path, self.sensor_id, self.sensor_type):
            var.trace_add('write', self._on_basic_changed)

        # test type changes update which test config fields are enabled
        self.test_type.trace_add('write', self._on_test_type_changed)

        self._setup_styles()
        self._create_widgets()
        self._update_sensor_id()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # styles
    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        PAGE_BG = "#eef2f7"
        CARD_BG = "#ffffff"
        DISABLED_BG = "#e8ebf0"
        DISABLED_FG = "#9aa1ad"
        FONT = "Helvetica"
        # all inputs and matching buttons share this internal padding so heights line up
        INPUT_PAD = (10, 7)
        # default: everything sits on the page bg
        style.configure(".", background=PAGE_BG, font=(FONT, 11))
        style.configure("TFrame", background=PAGE_BG)
        # frames inside cards use the card bg
        style.configure("Card.TFrame", background=CARD_BG)
        # title is on the page bg (above the cards)
        style.configure("Title.TLabel", background=PAGE_BG, font=(FONT, 22, "bold"))
        # everything else (section heading, field labels, captions, info icons, preview) lives inside cards
        style.configure("SectionHeading.TLabel", background=CARD_BG,
                        font=(FONT, 14, "bold"))
        style.configure("FieldLabel.TLabel", background=CARD_BG, font=(FONT, 11, "bold"))
        # plain 11pt text on a card — for value rows like 'Position: 17.00 mm'
        style.configure("CardText.TLabel", background=CARD_BG, font=(FONT, 11))
        style.configure("Caption.TLabel", background=CARD_BG, foreground="#666666",
                        font=(FONT, 9))
        style.configure("SegCaption.TLabel", background=CARD_BG, foreground="#5a6473",
                        font=(FONT, 9))
        style.configure("SegPrefix.TLabel", background=CARD_BG, foreground="#5a6473",
                        font=(FONT, 11, "bold"))
        style.configure("SensorPreview.TLabel", background=CARD_BG, foreground="#4163d1",
                        font=(FONT, 9))
        # info icons blend with the card bg, no white square behind them on the page bg
        style.configure("Info.TLabel", background=CARD_BG, foreground="#5a6473",
                        font=(FONT, 12))
        # match the input height by using the same vertical padding as INPUT_PAD
        style.configure("UnitSuffix.TLabel", background="#dce2ec", foreground="#5a6473",
                        padding=(10, INPUT_PAD[1]), font=(FONT, 9))
        # entries / comboboxes / spinbox share padding + font so they match each other and the buttons
        # insertcolor gives the blinking text cursor a visible color when focused
        # disabled state is visibly grayed out
        for name in ("Input.TEntry", "Input.TCombobox", "Input.TSpinbox"):
            style.configure(name, fieldbackground=CARD_BG, padding=INPUT_PAD,
                            font=(FONT, 11), insertcolor="#1a1f2c")
            style.map(name,
                      fieldbackground=[("disabled", DISABLED_BG), ("readonly", CARD_BG)],
                      foreground=[("disabled", DISABLED_FG)],
                      background=[("disabled", DISABLED_BG)])
        # blue verify button; same height as the entries
        style.configure("Primary.TButton", padding=INPUT_PAD, background="#3a5dd9",
                        foreground="#ffffff", font=(FONT, 11, "bold"))
        style.map("Primary.TButton",
                  background=[('active', '#314fb8'), ('disabled', '#b6c1e6')])
        style.configure("Green.TButton", padding=INPUT_PAD, background="#3da556",
                        foreground="#ffffff", font=(FONT, 11, "bold"))
        style.map("Green.TButton",
                  background=[('active', '#358a47'), ('disabled', '#a8c2ad')])
        style.configure("Outline.TButton", padding=INPUT_PAD, font=(FONT, 11, "bold"))
        style.configure("Nav.TButton", padding=(12, 6), font=(FONT, 11, "bold"))
        # checkbutton font matches the field labels and sits on the card bg
        style.configure("TCheckbutton", background=CARD_BG, font=(FONT, 11, "bold"))

    # sensor id helpers
    def _update_sensor_id(self, *args):
        if self.use_custom_sensor_id.get():
            new_value = self.custom_sensor_id.get().strip()
        else:
            yy = self.sensor_year.get()
            mm = self.sensor_month.get()
            dd = self.sensor_day.get()
            b = self.sensor_batch.get()
            s = self.sensor_number.get()
            loc = self.sensor_location.get().upper()
            if yy and mm and dd and b and s and loc:
                new_value = f"{yy}{mm}{dd}B{b}S{s}{loc}"
            else:
                new_value = ""
        # only fire the trace if the value actually changed
        # paths (like re-enabling widgets after a test starts) would falsely trigger
        # _on_basic_changed and hide the test configuration card.
        if new_value != self.sensor_id.get():
            self.sensor_id.set(new_value)

        if self.sensor_preview_lbl is not None:
            sid = self.sensor_id.get()
            if self._is_valid_sensor_id(sid):
                self.sensor_preview_lbl.config(text=f"Sensor ID: {sid}", foreground="#4163d1")
            else:
                self.sensor_preview_lbl.config(text="Sensor ID: complete all segments", foreground="#999999")

    @staticmethod
    def _is_valid_sensor_id(sid):
        return bool(SENSOR_ID_PATTERN.match(sid.strip()))

    def _toggle_custom_sensor(self):
        use_custom = self.use_custom_sensor_id.get()
        anchor = getattr(self, "sensor_custom_row", None)
        if use_custom:
            # hide builder + preview; show custom entry in their place (above the checkbox).
            if self.sensor_builder_frame is not None:
                self.sensor_builder_frame.pack_forget()
            if self.sensor_preview_row is not None:
                self.sensor_preview_row.pack_forget()
            if self.custom_sensor_entry is not None and anchor is not None:
                # left-anchored at natural width so it visually matches the builder size
                self.custom_sensor_entry.pack(anchor="w", pady=(6, 4), before=anchor)
                self.custom_sensor_entry.config(state="normal")
        else:
            if self.custom_sensor_entry is not None:
                self.custom_sensor_entry.pack_forget()
            if self.sensor_builder_frame is not None and anchor is not None:
                self.sensor_builder_frame.pack(anchor="w", pady=(6, 0), before=anchor)
            if self.sensor_preview_row is not None and anchor is not None:
                self.sensor_preview_row.pack(anchor="w", fill="x", pady=(8, 4), before=anchor)
        self._update_sensor_id()

    # verification + reverification behavior (story 1.1.7, 1.1.8)
    def _on_basic_changed(self, *args):
        # only invalidate verification when a basic-settings value ACTUALLY differs
        # from what was verified. programmatic .set() calls that pass the same value
        # (e.g. re-enabling widgets after a test starts) should not count as edits.
        if not self.settings_verified.get():
            return
        snap = getattr(self, "_verified_snapshot", None)
        current = (self.saved_path.get(), self.sensor_id.get(), self.sensor_type.get())
        if snap is not None and current == snap:
            return
        self.settings_verified.set(False)
        self._hide_test_config()
        self._show_changed_banner("Basic settings changed. Please click Verify again.")
        self._hide_folder_banner()

    def verify_settings(self):
        folder = self.saved_path.get().strip()
        sid = self.sensor_id.get().strip()

        if not folder:
            self.error("Fill in Save Folder before continuing.")
            return
        if self.use_custom_sensor_id.get() and not sid:
            self.error("Enter a custom sensor ID.")
            return
        if not sid:
            self.error("Complete all Sensor ID segments before continuing.")
            return
        if not self.use_custom_sensor_id.get() and not self._is_valid_sensor_id(sid):
            self.error(f"Sensor ID '{sid}' is not in the format YYMMDDB##S##X (X = A, B, AB, or BA).")
            return
        if not self.sensor_type.get().strip():
            self.error("Fill in Sensor Type before continuing.")
            return

        if self.is_create_files.get():
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.error(f"Could not create folder: {e}")
                return

        # snapshot the verified state so spurious .set() with the same values
        self._verified_snapshot = (
            self.saved_path.get(),
            self.sensor_id.get(),
            self.sensor_type.get(),
        )
        self.settings_verified.set(True)
        self._hide_changed_banner()
        self._show_folder_banner()
        self._show_test_config()

    # folder banner + changed banner
    def _compute_test_folder(self, version_suffix=""):
        """Return the expected output folder path: {save}/{sensor}/{MM DD YY}_{SA}_{Test}{suffix}"""
        save = self.saved_path.get().strip()
        sid = self.sensor_id.get().strip()
        if not save or not sid:
            return None
        now = datetime.now()
        date_str = f"{str(now.month).zfill(2)} {str(now.day).zfill(2)} {str(now.year)[2:]}"
        sa = self.surface_area.get().strip() or "0"
        test = (self.test_type.get() or "EM Test").replace(" Test", "").strip() or "EM"
        return Path(save) / sid / f"{date_str}_{sa}mm2_{test}{version_suffix}"

    def _show_folder_banner(self):
        path = self._compute_test_folder()
        if path is None or self.folder_banner_lbl is None:
            return
        self.folder_banner_text.set(f"Folder path: {path}")
        self.folder_banner_lbl.pack(fill="x", pady=(0, 10), before=self.basic_settings_card)
        self._reflow_scroll()

    def _hide_folder_banner(self):
        if self.folder_banner_lbl is not None:
            self.folder_banner_lbl.pack_forget()
            self._reflow_scroll()

    def _show_changed_banner(self, text):
        if self.changed_banner_frame is None:
            return
        self.changed_banner_text.set(text)
        self.changed_banner_frame.pack(fill="x", pady=(0, 10), before=self.basic_settings_card)
        self._reflow_scroll()

    def _hide_changed_banner(self):
        if self.changed_banner_frame is not None:
            self.changed_banner_frame.pack_forget()
            self._reflow_scroll()

    def _show_test_config(self):
        if self.test_config_card is not None:
            self.test_config_card.pack(fill="x", pady=(0, 14))
            self._on_test_type_changed()
            self._reflow_scroll()

    def _hide_test_config(self):
        if self.test_config_card is not None:
            self.test_config_card.pack_forget()
            self._reflow_scroll()

    def _reflow_scroll(self):
        # dynamic content visibility changed — recompute scroll_frame height so
        # scrollregion grows enough to include the new content.
        fn = getattr(self, "_reconfigure_scroll", None)
        if fn is not None:
            fn()

    # test type field rules (story 1.3.2)
    def _on_test_type_changed(self, *args):
        if not self.test_config_widgets:
            return
        t = self.test_type.get()

        # auto-fill surface area for shear (50.27) and reset to 325 for the others,
        # but only if the field still holds one of the known defaults — preserves any custom value
        known_defaults = {"325", "50.27"}
        if self.surface_area.get().strip() in known_defaults:
            self.surface_area.set("50.27" if t == "Shear Test" else "325")

        # dropdown-style inputs use 'arrow' when enabled; entries/spinbox use 'xterm' (i-beam)
        combo_names = ("zaber_comport", "test_type")

        def enable(name, on):
            w = self.test_config_widgets.get(name)
            if w is None:
                return
            if on:
                state = "readonly" if name in combo_names else "normal"
                cursor = "arrow" if name in combo_names else "xterm"
                w.config(state=state, cursor=cursor)
            else:
                # 'X_cursor' is the cross-platform tk name for the not-allowed indicator
                w.config(state="disabled", cursor="X_cursor")

        if t == "EM Test":
            enable("n_runs", not self.redo_mode.get())
            enable("zaber_comport", True)
        elif t == "Shear Test":
            enable("n_runs", False)
            enable("zaber_comport", False)
        else:
            enable("n_runs", False)
            enable("zaber_comport", True)

        # run to redo only enabled in redo mode and em test
        enable("run_to_redo", self.redo_mode.get() and t == "EM Test")

        # in redo mode, test type locked to em
        tt = self.test_config_widgets.get("test_type")
        if tt is not None:
            if self.redo_mode.get():
                tt.config(state="disabled", cursor="X_cursor")
            else:
                tt.config(state="readonly", cursor="arrow")

    # existing test found popup (story 1.2.x)
    def _on_begin_test_clicked(self):
        # validate test config
        if not self.test_type.get().strip():
            self.error("Fill in Test Type before continuing.")
            return
        if self.test_type.get() == "EM Test":
            try:
                n = int(self.n_runs.get())
                if n < 1:
                    raise ValueError
            except (ValueError, tk.TclError):
                self.error("Number of Runs must be a positive integer.")
                return
        if self.test_type.get() in ("EM Test", "Manual Test", "Cyclical Test"):
            if not self.zaber_comport.get().strip():
                self.error("Fill in Zaber COM Port before continuing.")
                return
        try:
            sa = float(self.surface_area.get())
            if sa <= 0:
                raise ValueError
        except ValueError:
            self.error("Surface Area must be a positive number.")
            return
        if self.redo_mode.get():
            try:
                rr = int(self.run_to_redo.get())
                if rr < 1:
                    raise ValueError
            except (ValueError, tk.TclError):
                self.error("Run to Redo must be a positive integer.")
                return

        # cyclical creates and saves nothing
        if self.test_type.get() == "Cyclical Test":
            self._start_test()
            return

        # check existing folder for all other test types
        target = self._compute_test_folder()
        if target is not None and target.exists() and self.existing_test_action.get() == "":
            self._show_existing_test_popup(target)
            return

        # otherwise start the test
        self._start_test()

    def _show_existing_test_popup(self, target_path):
        popup = tk.Toplevel(self.root)
        popup.title("Existing Test Found")
        popup.configure(bg="#ffffff")
        popup.geometry("640x320")
        popup.resizable(False, False)
        popup.grab_set()

        header = tk.Label(popup, text="Existing Test Found",
                          bg="#ffffff", fg="#1a1f2c",
                          font=("Helvetica", 14, "bold"))
        header.pack(anchor="w", padx=20, pady=(20, 8))

        ttk.Separator(popup).pack(fill="x", padx=20)

        info = tk.Label(
            popup,
            text=(f"A test folder exists for this Sensor ID:\n{target_path}\n\n"
                  "Choose how you want to continue."),
            bg="#e7efff", fg="#3856b3",
            font=("Helvetica", 9),
            padx=12, pady=10,
            justify="left", wraplength=580, anchor="w",
        )
        info.pack(fill="x", padx=20, pady=12)

        is_em = self.test_type.get() == "EM Test"

        btn_grid = tk.Frame(popup, bg="#ffffff")
        btn_grid.pack(fill="x", padx=20, pady=(4, 16))
        btn_grid.grid_columnconfigure(0, weight=1)
        btn_grid.grid_columnconfigure(1, weight=1)

        def on_versioned():
            popup.destroy()
            self.existing_test_action.set("versioned")
            self._start_test()

        def on_overwrite():
            if messagebox.askokcancel(
                "Overwrite Existing Test",
                f"Overwrite existing data in {target_path}?\n\nThis cannot be undone.",
                icon="warning", parent=popup,
            ):
                popup.destroy()
                self.existing_test_action.set("overwrite")
                self._start_test()

        def on_redo():
            popup.destroy()
            self.redo_mode.set(True)
            self.test_type.set("EM Test")
            self.n_runs.set(1)
            self.existing_test_action.set("redo")
            self._on_test_type_changed()

        def on_cancel():
            popup.destroy()
            self.update_textbox("Verification cancelled. No test folder changes were made.")

        tk.Button(btn_grid, text="Create New Versioned Test Folder",
                  command=on_versioned, bg="#3a5dd9", fg="#ffffff",
                  font=("Helvetica", 11, "bold"), padx=12, pady=10,
                  bd=0, activebackground="#314fb8", activeforeground="#ffffff").grid(
            row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))

        redo_btn = tk.Button(btn_grid, text="Redo a Specific Run", command=on_redo,
                             bg="#ffffff", fg="#1a1f2c" if is_em else "#a0a0a0",
                             font=("Helvetica", 11, "bold"), padx=12, pady=10,
                             bd=1, relief="solid",
                             state=tk.NORMAL if is_em else tk.DISABLED)
        redo_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        tk.Button(btn_grid, text="Overwrite Existing Test",
                  command=on_overwrite, bg="#c14545", fg="#ffffff",
                  font=("Helvetica", 11, "bold"), padx=12, pady=10,
                  bd=0, activebackground="#a83b3b", activeforeground="#ffffff").grid(
            row=1, column=0, sticky="ew", padx=(0, 6))

        tk.Button(btn_grid, text="Cancel", command=on_cancel,
                  bg="#ffffff", fg="#1a1f2c",
                  font=("Helvetica", 11, "bold"), padx=12, pady=10,
                  bd=1, relief="solid").grid(row=1, column=1, sticky="ew", padx=(6, 0))

    def _start_test(self):
        # compute the intended target path but do NOT create folders here.
        # per acceptance criteria: no files/folders are created until perform analysis runs.
        # cyclical does not save anything at all, so it gets no target path.
        action = self.existing_test_action.get()
        test_type = self.test_type.get()

        if test_type == "Cyclical Test":
            target = None
        else:
            target = self._compute_test_folder()
            if action == "versioned":
                # next available _1, _2, _3 ... without stacking suffixes
                i = 1
                while True:
                    candidate = self._compute_test_folder(version_suffix=f"_{i}")
                    if not candidate.exists():
                        target = candidate
                        break
                    i += 1

        # store intended path so the test window / analysis step can use it later
        self.pending_target_path = target
        self.existing_test_action.set("")

        if target is not None:
            self.update_textbox(f"Test folder will be: {target} (created when analysis runs)")
        else:
            self.update_textbox("Cyclical test — no folder will be created.")

        # kick off the test via existing trace_test routing
        if self.pause_btn is not None:
            self.pause_btn.config(state=tk.NORMAL)
        self.is_test_started.set(1)

    # info icon tooltip helper (story 1.1.9, 1.3.9)
    def _info_icon(self, parent, tooltip_text):
        # ttk.label picks up the page bg from Info.TLabel, so no white square shows behind it
        lbl = ttk.Label(parent, text="ⓘ", style="Info.TLabel", cursor="hand2")
        self._attach_tooltip(lbl, tooltip_text)
        return lbl

    def install_mousewheel(self, canvas):
        # binds mousewheel scroll to the given canvas.
        # bind_all alone doesn't work on macos because ttk entry/combobox/spinbox
        # consume mousewheel events at the class level. binding on the canvas and on
        # every descendant widget at the instance level makes sure scroll fires first.
        import sys
        is_mac = sys.platform == "darwin"

        def on_mousewheel(event):
            if is_mac:
                canvas.yview_scroll(-event.delta, "units")
            else:
                canvas.yview_scroll(int(-event.delta / 120) * 3, "units")

        def on_button4(_):
            canvas.yview_scroll(-3, "units")
        def on_button5(_):
            canvas.yview_scroll(3, "units")

        # global fallback for widgets that don't consume the event
        self.root.bind_all("<MouseWheel>", on_mousewheel)
        self.root.bind_all("<Button-4>", on_button4)
        self.root.bind_all("<Button-5>", on_button5)

        # instance-level bindings on every widget under the canvas so scroll works
        # even when the cursor sits on a ttk input that would otherwise swallow it
        self._bind_mousewheel_tree(canvas, on_mousewheel, on_button4, on_button5)

    def _bind_mousewheel_tree(self, root_widget, mw_handler, b4_handler, b5_handler):
        if isinstance(root_widget, (tk.Text, tk.Listbox)):
            return
        try:
            root_widget.bind("<MouseWheel>", mw_handler)
            root_widget.bind("<Button-4>", b4_handler)
            root_widget.bind("<Button-5>", b5_handler)
        except tk.TclError:
            return
        for child in root_widget.winfo_children():
            self._bind_mousewheel_tree(child, mw_handler, b4_handler, b5_handler)

    def restore_main_mousewheel(self):
        if getattr(self, "_main_canvas", None) is not None:
            self.install_mousewheel(self._main_canvas)

    @staticmethod
    def _clear_combo_highlight(event):
        try:
            event.widget.selection_clear()
            event.widget.master.focus_set()
        except tk.TclError:
            pass

    def _attach_tooltip(self, widget, text):
        tooltip = tk.Toplevel(widget)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tk.Label(tooltip, text=text, bg="#fff7e6", fg="#3b3f47",
                 padx=10, pady=6, relief="solid", borderwidth=1,
                 wraplength=320, justify="left",
                 font=("Helvetica", 9)).pack()

        def show(event):
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 22
            tooltip.geometry(f"+{x}+{y}")
            tooltip.deiconify()

        def hide(event):
            tooltip.withdraw()

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _labeled(self, parent, text, tooltip):
        # label + info-icon row inside a white card
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(anchor="w", fill="x")
        ttk.Label(row, text=text, style="FieldLabel.TLabel").pack(side="left")
        if tooltip:
            self._info_icon(row, tooltip).pack(side="left", padx=(6, 0))
        return row

    # activity textbox (kept hidden; preserves existing logic until phase 5)
    def display_updates(self, parent):
        """Hidden activity log; only visible if a test runs while EM Testing Window
        is not yet implemented. Phase 5 will route status to the dedicated window."""
        textbox = scrolledtext.ScrolledText(parent, height=6,
                                            borderwidth=1, relief='sunken')
        textbox.pack(fill="both", expand=True)
        textbox.config(state=tk.DISABLED)
        self.textbox = textbox

    def update_textbox(self, text):
        print(text)
        if self.textbox is not None:
            try:
                self.textbox.config(state=tk.NORMAL)
                self.textbox.insert(tk.END, f"{text}\n")
                self.textbox.config(state=tk.DISABLED)
            except tk.TclError:
                pass

    # test traces / start / pause / end
    def trace_test(self, *args):
        test_start = self.is_test_started.get()
        test_type = self.test_type.get()
        if test_start:
            for w in self.widgets:
                try:
                    w.config(state=tk.DISABLED)
                except tk.TclError:
                    pass
            if test_type == "EM Test":
                if self.pause_btn is not None:
                    self.pause_btn.config(state=tk.NORMAL)
                from em_test_window import EMTestWindow
                EMTestWindow(self.root, self)
                # clear the started flag so re-clicking begin test reopens the window
                self.is_test_started.set(0)
            elif test_type == "Shear Test":
                if self.pause_btn is not None:
                    self.pause_btn.config(state=tk.DISABLED)
                self._shear_test()
        else:
            for w in self.widgets:
                try:
                    w.config(state=tk.NORMAL)
                except tk.TclError:
                    pass
            self._toggle_custom_sensor()

    def trace_pause(self, *args):
        self.update_pause_btn()

    def _shear_test(self):
        # phase 6: dedicated shear testing window with simulated preview run
        from shear_window import ShearWindow
        ShearWindow(self.root, self)
        # clear started flag so begin test can reopen
        self.is_test_started.set(0)

    def _EM_test(self):
        if not (self.is_test_started.get() and self.toggle_pause.get() == 0):
            return

        n_runs = self.n_runs.get()
        current_run = self.current_run.get()

        self.update_textbox(f"Beginning run {current_run}")
        state = self.test_funct(n_runs, current_run, self.saved_path.get(),
                                self.sensor_id.get(), self.zaber_comport.get())

        is_paused = current_run == state
        self.update_textbox(f"Run {current_run} was paused" if is_paused
                           else f"Run {current_run} completed")

        if current_run == n_runs and not is_paused:
            self.update_textbox("All runs complete")
            self._end_testing()
        else:
            self.current_run.set(state)
            if state <= n_runs:
                self.toggle_pause.set(1)
                self.update_pause_btn()

    def _end_testing(self):
        self.testing_complete()
        self.is_test_started.set(0)
        self.current_run.set(1)

    def _helper_pause(self, *args):
        if self.toggle_pause.get() == 0:
            self.toggle_pause.set(1)
        elif self.toggle_pause.get() == 1:
            self.toggle_pause.set(0)
            self._EM_test()

    def update_pause_btn(self, *args):
        if self.pause_btn is None:
            return
        if self.toggle_pause.get() == 0:
            self.pause_btn.config(text="Pause Run")
        else:
            self.pause_btn.config(text="Unpause Run")

    # page-level nav buttons (no styled bar — sit on the page bg)
    def navbar(self, parent):
        def open_control():
            zaber = ZaberCLI()
            control = ControlWindow(self.root, self, zaber)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 12))
        ttk.Button(row, text='Main Stage', style="Nav.TButton",
                   state=tk.DISABLED).pack(side="left", padx=(0, 6))
        ttk.Button(row, text='Control Panel', style="Nav.TButton",
                   command=open_control).pack(side="left")

    # basic settings card widgets
    def select_folder(self, parent):
        def open_folder():
            file_path = fd.askdirectory()
            if file_path:
                self.saved_path.set(file_path)

        self._labeled(parent, "Save Folder",
                      "Where test outputs (Excel files, plots, analysis results) are saved.")

        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 2))
        folder_entry = ttk.Entry(row, textvariable=self.saved_path, style="Input.TEntry",
                                 cursor="xterm")
        folder_entry.pack(side="left", fill="x", expand=True)
        open_button = ttk.Button(row, text='Browse', command=open_folder, style="Outline.TButton")
        open_button.pack(side="left", padx=(8, 0))
        ttk.Label(parent,
                  text="Missing folders will be automatically created before a run.",
                  style="Caption.TLabel").pack(anchor="w", pady=(2, 10))

        self.widgets.append(folder_entry)
        self.widgets.append(open_button)

    def enter_sensor_id(self, parent):
        self._labeled(parent, "Sensor ID",
                      "Format: YYMMDDB##S##X. Two digits for year, month, day, batch, and sensor. "
                      "Location can be A, B, AB, or BA.")

        builder = tk.Frame(parent, bg="#ffffff", highlightthickness=1,
                           highlightbackground="#cdd3de", highlightcolor="#cdd3de")
        builder.pack(anchor="w", pady=(6, 0))
        self.sensor_builder_frame = builder

        def add_segment(caption, var, kind, prefix=None, is_last=False):
            cell = tk.Frame(builder, bg="#ffffff", padx=10, pady=4, cursor="xterm")
            cell.pack(side="left")
            tk.Label(cell, text=caption, bg="#ffffff", fg="#5a6473",
                     font=("Helvetica", 8)).pack()
            inner = tk.Frame(cell, bg="#ffffff")
            inner.pack()
            if prefix:
                tk.Label(inner, text=prefix, bg="#ffffff", fg="#5a6473",
                         font=("Helvetica", 11, "bold")).pack(side="left", padx=(0, 2))
            width = 4 if kind == "location" else 3
            entry = tk.Entry(inner, width=width, justify="center",
                             font=("Helvetica", 11, "bold"),
                             bd=0, relief="flat", bg="#ffffff",
                             highlightthickness=0, cursor="xterm",
                             insertbackground="#1a1f2c", insertwidth=2)
            entry.pack(side="left")
            self._wire_sensor_segment(entry, var, kind)
            self.widgets.append(entry)
            self.sensor_segment_entries.append(entry)
            if not is_last:
                sep = tk.Frame(builder, bg="#dce2ec", width=1)
                sep.pack(side="left", fill="y", padx=0)

        add_segment("YY",       self.sensor_year,     "year")
        add_segment("MM",       self.sensor_month,    "month")
        add_segment("DD",       self.sensor_day,      "day")
        add_segment("Batch",    self.sensor_batch,    "batch",    prefix="B")
        add_segment("Sensor",   self.sensor_number,   "sensor",   prefix="S")
        add_segment("Location", self.sensor_location, "location", is_last=True)

        # preview row (hidden in custom mode)
        self.sensor_preview_row = ttk.Frame(parent, style="Card.TFrame")
        self.sensor_preview_row.pack(anchor="w", fill="x", pady=(8, 4))
        self.sensor_preview_lbl = ttk.Label(self.sensor_preview_row, text="",
                                            style="SensorPreview.TLabel")
        self.sensor_preview_lbl.pack(anchor="w")

        # custom sensor id entry
        self.custom_sensor_entry = ttk.Entry(parent, textvariable=self.custom_sensor_id,
                                             style="Input.TEntry", cursor="xterm",
                                             width=28)
        # pack invisibly initially; _toggle_custom_sensor controls visibility.
        self.widgets.append(self.custom_sensor_entry)

        # use custom sensor id checkbox
        custom_row = ttk.Frame(parent, style="Card.TFrame")
        custom_row.pack(anchor="w", fill="x", pady=(4, 0))
        self.sensor_custom_row = custom_row
        custom_check = ttk.Checkbutton(custom_row, text="Use Custom Sensor ID",
                                       variable=self.use_custom_sensor_id,
                                       command=self._toggle_custom_sensor)
        custom_check.pack(side="left")
        self._info_icon(custom_row,
                        "When enabled, the Sensor ID builder is replaced with a free-text custom Sensor ID field.").pack(
            side="left", padx=(6, 0))
        self.widgets.append(custom_check)

    def _wire_sensor_segment(self, entry, var, kind):
        """Attach placeholder behavior + input validation to a sensor ID segment entry."""
        placeholder = self.sensor_placeholders[kind]
        max_len = 4 if kind == "location" else 2

        # state held on the widget so callbacks can find it.
        entry._placeholder = placeholder
        entry._placeholder_active = False
        entry._sensor_var = var
        entry._suppress_validation = False

        def show_placeholder():
            entry._suppress_validation = True
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)
            entry.config(fg="#bbbbbb")
            entry._placeholder_active = True
            entry._suppress_validation = False

        def clear_placeholder():
            if entry._placeholder_active:
                entry._suppress_validation = True
                entry.delete(0, tk.END)
                entry.config(fg="#1a1f2c")
                entry._placeholder_active = False
                entry._suppress_validation = False

        def on_focus_in(_):
            clear_placeholder()

        def on_focus_out(_):
            text = entry.get().strip()
            if kind == "location":
                text = text.upper()
                entry._suppress_validation = True
                entry.delete(0, tk.END)
                entry.insert(0, text)
                entry._suppress_validation = False
            if not text:
                show_placeholder()
                var.set("")
            else:
                var.set(text)

        def on_key_release(event):
            if entry._placeholder_active:
                return
            value = entry.get()
            var.set(value)
            # auto-advance to the next segment once this one is full
            # (skip on backspace/delete/tab/arrow keys so we don't yank focus while editing)
            if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Tab", "Shift_L", "Shift_R"):
                return
            target_len = 2 if kind != "location" else 2
            if len(value) >= target_len:
                try:
                    idx = self.sensor_segment_entries.index(entry)
                except ValueError:
                    return
                if idx + 1 < len(self.sensor_segment_entries):
                    self.sensor_segment_entries[idx + 1].focus_set()

        def validate(proposed):
            if entry._suppress_validation:
                return True
            if len(proposed) > max_len:
                return False
            if not proposed:
                return True
            if kind == "location":
                upper = proposed.upper()
                if upper in ("A", "B", "AB", "BA"):
                    return True
                return False
            # numeric segments: digits only
            return proposed.isdigit()

        vcmd = (entry.register(validate), '%P')
        entry.config(validate="key", validatecommand=vcmd)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        entry.bind("<KeyRelease>", on_key_release)

        # start in placeholder state.
        show_placeholder()

    def select_sensor_type(self, parent):
        self._labeled(parent, "Sensor Type",
                      "Channel ordering. Standard: [1..8]. Inverted: reverses the channel mapping.")
        sensor_entry = ttk.Combobox(parent, textvariable=self.sensor_type,
                                    values=["Standard", "Inverted"], state="readonly",
                                    style="Input.TCombobox", cursor="arrow")
        sensor_entry.pack(fill="x", pady=(6, 10))
        sensor_entry.bind("<<ComboboxSelected>>", self._clear_combo_highlight)
        self.widgets.append(sensor_entry)

    def add_separator(self, y_value, window):
        separator = ttk.Separator(window)
        separator.place(x=0, y=y_value, relwidth=1)

    # verify button
    def verify_btn(self, parent):
        # same padding as begin test so the two primary buttons line up in height
        btn = ttk.Button(parent, text="Verify", command=self.verify_settings, style="Primary.TButton")
        btn.pack(fill="x", pady=(10, 0))
        self.widgets.append(btn)

    # test configuration card (story 1.3.x) 
    def _build_test_config_card(self, container):
        # white card wrapper with subtle border
        card = tk.Frame(container, bg="#ffffff",
                        highlightthickness=1,
                        highlightbackground="#dde2eb",
                        highlightcolor="#dde2eb")
        self.test_config_card = card

        inner = ttk.Frame(card, padding=(20, 18, 20, 18), style="Card.TFrame")
        inner.pack(fill="x")

        ttk.Label(inner, text="Test Configuration",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 10))

        grid = ttk.Frame(inner, style="Card.TFrame")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="tc")
        grid.grid_columnconfigure(1, weight=1, uniform="tc")

        # row 0: test type | surface area
        tt_frame = ttk.Frame(grid, style="Card.TFrame")
        tt_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 10))
        self._labeled(tt_frame, "Test Type",
                      "Selects the testing workflow and analysis pipeline.")
        test_combo = ttk.Combobox(
            tt_frame, textvariable=self.test_type,
            values=["EM Test", "Shear Test", "Manual Test", "Cyclical Test"],
            state="readonly", style="Input.TCombobox", cursor="arrow")
        test_combo.pack(fill="x", pady=(6, 0))
        test_combo.bind("<<ComboboxSelected>>", self._clear_combo_highlight)
        self.test_config_widgets["test_type"] = test_combo

        sa_frame = ttk.Frame(grid, style="Card.TFrame")
        sa_frame.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        self._labeled(sa_frame, "Surface Area",
                      "Ecoflex block surface area used to convert force readings to pressure.")
        sa_row = ttk.Frame(sa_frame, style="Card.TFrame")
        sa_row.pack(fill="x", pady=(6, 0))
        sa_entry = ttk.Entry(sa_row, textvariable=self.surface_area, style="Input.TEntry",
                             cursor="xterm")
        sa_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(sa_row, text="mm²", style="UnitSuffix.TLabel").pack(side="left", padx=(6, 0))
        self.test_config_widgets["surface_area"] = sa_entry

        # row 1: number of runs | zaber com port
        runs_frame = ttk.Frame(grid, style="Card.TFrame")
        runs_frame.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(0, 10))
        self._labeled(runs_frame, "Number of Runs",
                      "How many test runs to perform. Only enabled for EM Test.")
        runs_entry = ttk.Spinbox(runs_frame, from_=1, to=100, textvariable=self.n_runs,
                                 style="Input.TSpinbox", cursor="xterm")
        runs_entry.pack(fill="x", pady=(6, 0))
        self.test_config_widgets["n_runs"] = runs_entry

        com_frame = ttk.Frame(grid, style="Card.TFrame")
        com_frame.grid(row=1, column=1, sticky="ew", pady=(0, 10))
        self._labeled(com_frame, "Zaber COM Port",
                      "Serial port used to communicate with the Zaber actuator.")
        com_values = self._available_comports()
        com_combo = ttk.Combobox(com_frame, textvariable=self.zaber_comport,
                                 values=com_values, state="readonly",
                                 style="Input.TCombobox", cursor="arrow")
        com_combo.pack(fill="x", pady=(6, 0))
        com_combo.bind("<<ComboboxSelected>>", self._clear_combo_highlight)
        self.test_config_widgets["zaber_comport"] = com_combo

        # row 2: run to redo
        rr_frame = ttk.Frame(grid, style="Card.TFrame")
        rr_frame.grid(row=2, column=0, sticky="ew", padx=(0, 12), pady=(0, 14))
        self._labeled(rr_frame, "Run to Redo",
                      "Only enabled when redoing a specific run from an existing test.")
        rr_entry = ttk.Entry(rr_frame, textvariable=self.run_to_redo, state="disabled",
                             style="Input.TEntry", cursor="xterm")
        rr_entry.pack(fill="x", pady=(6, 0))
        self.test_config_widgets["run_to_redo"] = rr_entry

        # action row: begin test (green) + open calibration side-by-side, splitting the row 50/50
        actions = ttk.Frame(inner, style="Card.TFrame")
        actions.pack(fill="x", pady=(4, 0))
        begin_btn = ttk.Button(actions, text="Begin Test", style="Green.TButton",
                               command=self._on_begin_test_clicked)
        begin_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        cal_btn = ttk.Button(actions, text="Open Calibration", style="Outline.TButton",
                             command=self._open_calibration)
        cal_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.test_config_widgets["begin_btn"] = begin_btn
        self.test_config_widgets["calibration_btn"] = cal_btn

        # apply initial enabled/disabled cursors + states once the widgets exist
        self._on_test_type_changed()

    def _available_comports(self):
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
            return ports or ["COM3"]
        except Exception:
            return ["COM3"]

    def _open_calibration(self):
        from calibration_window import CalibrationWindow
        CalibrationWindow(self.root, self)

    # dialogs (unchanged behavior, slight visual polish)
    def error(self, text):
        messagebox.showerror("Error", text, parent=self.root)

    def warning(self, text):
        result = messagebox.askokcancel("Warning", text, parent=self.root)
        self.is_warning_cancel.set(0 if result else 1)
        return result

    def perform_analysis(self, *args):
        # folders/data/outputs are created here — not on verify or begin test (per criteria)
        test_type = self.test_type.get()
        sensor_type = self.sensor_type.get()

        target = self.pending_target_path
        if target is not None:
            try:
                (target / "FUT").mkdir(parents=True, exist_ok=True)
                (target / "CAP").mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.error(f"Could not create analysis folder: {e}")
                return
            # downstream analysis code reads from saved_path; point it at fut now
            self.saved_path.set(str(target / "FUT"))

        if test_type.startswith("EM"):
            analysis = EMAnalysis(self.saved_path.get(), self.sensor_id.get(), sensor_type=sensor_type)
            analysis.save_data()
        elif test_type.startswith("Shear"):
            analysis = ShearAnalysis(self.saved_path.get(), self.sensor_id.get())
            analysis.run_full_analysis()

    def testing_complete(self):
        def new_test(*args):
            complete.grab_release()
            complete.withdraw()
        complete = tk.Toplevel(self.root)
        complete.title("Testing complete")
        complete.geometry("650x150")
        complete.resizable(False, False)
        complete.grab_set()

        sensor = self.sensor_id.get()
        tk.Label(complete,
                 text=f"All Runs have been completed for sensor {sensor}.",
                 padx=20, pady=20).pack()

        btn_row = tk.Frame(complete)
        btn_row.pack()
        tk.Button(btn_row, text="Exit", command=self.root.destroy,
                  width=10).pack(side="left", padx=5, pady=10)
        tk.Button(btn_row, text="New Test", command=new_test,
                  width=10).pack(side="left", padx=5, pady=10)
        tk.Button(btn_row, text="Perform Analysis", command=self.perform_analysis,
                  width=18).pack(side="left", padx=5, pady=10)

    # test functions
    def test_funct(self, n_runs, current_run, folder_path, sensor, zaber_comport):
        if current_run < n_runs:
            for i in range(1):
                if self.toggle_pause.get() == 1:
                    self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                    if self.is_warning_cancel.get() == 0:
                        return current_run
                    self.toggle_pause.set(0)
                time.sleep(1)
                self.root.update()
            return int(current_run) + 1
        elif current_run == n_runs:
            for i in range(1):
                if self.toggle_pause.get() == 1:
                    return current_run
                time.sleep(1)
                self.root.update()
            return int(current_run) + 1

    def run_tests(self, n_runs, current_run, zaber_comport):
        speed = 0.5
        upper_limit = 20
        Extract = 12.75
        isNewerUSB225 = 1

        zaber = ZaberCLI()
        connection = zaber.connect(comport=zaber_comport)
        if connection == 0:
            print("Cannot Connect to Zaber comport")
            self.error("Cannot Connect to Zaber comport")
            return
        futek = FUTEKDeviceCLI()

        zaber.axis.move_relative((Extract-1.8), Units.LENGTH_MILLIMETRES)

        currentPosition = zaber.axis.get_position()
        currentPosition_mm = (currentPosition*0.047625)/1000

        init_force = 1
        force_readings = [0] * 12000
        init_time = datetime.now()
        init_seconds = init_time.second + init_time.microsecond / 1e6

        if zaber.axis.is_parked():
            zaber.axis.unpark()
        zaber.axis.move_velocity(speed*0.1, Units.VELOCITY_MILLIMETRES_PER_SECOND)
        init_val = 0
        force_idx = 0
        while True:
            if self.toggle_pause.get() == 1:
                self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                if self.is_warning_cancel.get() == 0:
                    zaber.axis.stop()
                    zaber.axis.wait_until_idle()
                    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
                    futek.stop()
                    futek.exit()
                    zaber.disconnect()
                    return current_run
                self.toggle_pause.set(0)
            self.root.update()

            reading_force = futek.getNormalData()
            if isNewerUSB225:
                reading_force = reading_force * (-4.44822)

            if init_force:
                init_val = reading_force
                init_force = 0

            stage_force = reading_force - init_val
            force_readings[force_idx] = stage_force
            force_idx = force_idx + 1
            print("Force Value: " + str(stage_force))

            if stage_force >= upper_limit:
                zaber.axis.stop()
                break

        zaber.axis.move_velocity(-speed*2, Units.VELOCITY_MILLIMETRES_PER_SECOND)
        while True:
            if self.toggle_pause.get() == 1:
                self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                if self.is_warning_cancel.get() == 0:
                    zaber.axis.stop()
                    zaber.axis.wait_until_idle()
                    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
                    futek.stop()
                    futek.exit()
                    zaber.disconnect()
                    return current_run
                self.toggle_pause.set(0)
            self.root.update()

            reading_force = futek.getNormalData()
            if isNewerUSB225:
                reading_force = reading_force * (-4.44822)

            stage_force = reading_force - init_val
            force_readings[force_idx] = stage_force
            force_idx = force_idx + 1

            curr_pos = zaber.axis.get_position()
            last_position = (curr_pos*0.047625)/1000
            if last_position <= (currentPosition*0.047625)/1000:
                zaber.axis.stop()
                break

        if zaber.axis.is_parked():
            zaber.axis.unpark()
        zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)

        path = Path(self.saved_path.get())
        file_name = "Run " + str(current_run) + ".xlsx"
        path = path / file_name
        workbook = xlsxwriter.Workbook(path)
        worksheet = workbook.add_worksheet(str(current_run))

        worksheet.write('A1', 'Index')
        worksheet.write('B1', 'Load Cell')
        worksheet.write('C1', 'Time')

        time = np.linspace(init_seconds,
                           (len(force_readings)-1) * 0.016 + init_seconds,
                           len(force_readings))

        for index in range(len(force_readings)):
            worksheet.write(index+1, 0, index + 1)
            worksheet.write(index+1, 1, force_readings[index])
            worksheet.write(index+1, 2, time[index])
        workbook.close()

        futek.stop()
        futek.exit()
        zaber.disconnect()
        return int(current_run) + 1

    # window construction
    def _create_widgets(self):
        # scrollable shell: canvas + vertical scrollbar wrap the whole page
        outer = tk.Frame(self.root, bg="#eef2f7")
        outer.pack(fill="both", expand=True)

        # yscrollincrement sets each "unit" to a small pixel count so trackpad scroll feels natural.
        canvas = tk.Canvas(outer, bg="#eef2f7", highlightthickness=0, bd=0,
                           yscrollincrement=8)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scroll_frame = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        # scroll_frame height = max(natural content, canvas height) so the action row
        # stays flush against the bottom (no empty strip below) while scrolling still
        # works when content overflows. after_idle defers until layout has settled.
        def _reconfigure():
            # flush any pending layout so winfo_reqheight reflects current content
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
        # expose reconfigure so dynamic content (test config card, banners) can trigger
        # a reflow when they map/unmap.
        self._reconfigure_scroll = schedule_reconfigure

        # remember the canvas so control_window can restore main's scroll on close
        self._main_canvas = canvas

        container = ttk.Frame(scroll_frame, padding=(20, 14, 20, 14))
        container.pack(fill="both", expand=True)

        # nav buttons row (plain inline buttons, no styled bar)
        self.navbar(container)

        # header row: title + preview pill
        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text="Zaber Stage Testing",
                  style="Title.TLabel").grid(row=0, column=0, sticky="w")

        pill = tk.Frame(header, bd=1, relief="solid", bg="#ffffff")
        pill.grid(row=0, column=1, sticky="e")
        tk.Label(pill,
                 text="Preview mode: connected to local Python when launched with run_web_gui.py",
                 bg="#ffffff", fg="#3b3f47",
                 padx=12, pady=6, font=("Helvetica", 9)).pack()

        # changed banner (initially hidden)
        self.changed_banner_frame = tk.Frame(container, bg="#fff3cd")
        tk.Label(self.changed_banner_frame, textvariable=self.changed_banner_text,
                 bg="#fff3cd", fg="#856404",
                 padx=12, pady=8, font=("Helvetica", 9)).pack(anchor="w")

        # folder banner (initially hidden)
        self.folder_banner_lbl = tk.Label(container,
                                          textvariable=self.folder_banner_text,
                                          bg="#e7efff", fg="#3856b3",
                                          padx=12, pady=8,
                                          font=("Helvetica", 9),
                                          anchor="w")

        # basic settings card: white block with subtle border + internal padding
        self.basic_settings_card = tk.Frame(container, bg="#ffffff",
                                            highlightthickness=1,
                                            highlightbackground="#dde2eb",
                                            highlightcolor="#dde2eb")
        self.basic_settings_card.pack(fill="x", pady=(0, 14))

        basic_inner = ttk.Frame(self.basic_settings_card, padding=(20, 18, 20, 18),
                                style="Card.TFrame")
        basic_inner.pack(fill="x")

        ttk.Label(basic_inner, text="Basic Settings",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 10))

        self.select_folder(basic_inner)

        two_col = ttk.Frame(basic_inner, style="Card.TFrame")
        two_col.pack(fill="x", pady=(4, 6))
        two_col.grid_columnconfigure(0, weight=2, uniform="cols")
        two_col.grid_columnconfigure(1, weight=1, uniform="cols")

        left_col = ttk.Frame(two_col, style="Card.TFrame")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.enter_sensor_id(left_col)

        right_col = ttk.Frame(two_col, style="Card.TFrame")
        right_col.grid(row=0, column=1, sticky="nsew")
        self.select_sensor_type(right_col)

        self.verify_btn(basic_inner)

        # test configuration card (hidden until verify)
        self._build_test_config_card(container)

        # hidden pause button (kept for compat with existing trace_test references)
        self.pause_btn = ttk.Button(container, text="Pause Run",
                                    command=self._helper_pause, state=tk.DISABLED)
        # intentionally not packed.

        # hidden activity textbox (compat fallback until phase 5 em testing window)
        hidden_holder = tk.Frame(container)
        # not packed; create the textbox inside it but never show.
        self.display_updates(hidden_holder)

        # trace bindings
        self.is_test_started.trace_add('write', self.trace_test)
        self.toggle_pause.trace_add('write', self.trace_pause)

        # now that every widget under the canvas exists, wire up mousewheel scrolling
        self.install_mousewheel(self._main_canvas)

    def on_close(self):
        self.root.destroy()

main = MainWindow()
main.root.mainloop()
