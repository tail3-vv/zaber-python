import tkinter as tk
from tkinter import ttk
import serial.tools.list_ports
from zaber_motion import Units
from zaber_cli import ZaberCLI

"""
Separate window for manually controlling the Zaber stage.
Lives as an overlay on top of the main window.
"""


class ControlWindow(tk.Frame):

    def __init__(self, root, main_window, zaber):
        super().__init__(root)
        self.root = root
        self.main_window = main_window
        self.zaber = zaber

        # overlay frame fills the root, picks up the page bg
        self.window = tk.Frame(self.root, bg="#eef2f7")
        self.window.place(relx=0, rely=0, relwidth=1, relheight=1)
        try:
            self.window.lift()
        except Exception:
            pass

        # zaber state
        self.zaber = ZaberCLI()
        self.default_pos = tk.IntVar(value=17)
        self.position = tk.IntVar(value=17)
        self.min_pos = tk.IntVar(value=17)
        self.max_pos = tk.IntVar(value=40)
        self.speed = tk.DoubleVar(value=0.5)
        self.zaber_comport = tk.StringVar(value="")
        # widgets disabled until a comport is picked
        self.widgets = []

        self._create_widgets()

        # everything starts disabled until a comport is chosen
        for w in self.widgets:
            try:
                w.config(state=tk.DISABLED)
            except tk.TclError:
                pass

        self.zaber_comport.trace_add('write', self.trace_comport)

    # logic — unchanged behaviour from original file
    def trace_comport(self, *args):
        for w in self.widgets:
            try:
                w.config(state=tk.NORMAL)
            except tk.TclError:
                pass
        print(f"Selected Zaber Comport: {self.zaber_comport.get()}")
        self.zaber.connect(self.zaber_comport.get())
        pos = self.zaber.axis.get_position()
        pos = (pos * 0.04765) / 1000
        self.position.set(pos)

    def save_inputs(self):
        print(f"Position changed to: {self.position.get()}")
        if self.position.get() < self.min_pos.get():
            self.position.set(self.min_pos.get())
        elif self.position.get() > self.max_pos.get():
            self.position.set(self.max_pos.get())
        self.zaber.axis.move_absolute(self.position.get(), Units.LENGTH_MILLIMETRES)

        min_pos = self.min_pos.get()
        print(f"Min position changed to: {min_pos}")
        if min_pos >= self.max_pos.get():
            self.min_pos.set(min_pos - 1)

        max_pos = self.max_pos.get()
        print(f"Max position changed to: {max_pos}")
        if self.max_pos.get() <= self.min_pos.get():
            self.max_pos.set(self.min_pos.get() + 1)

        if self.min_pos.get() < 17:
            self.min_pos.set(17)
        if self.max_pos.get() > 40:
            self.max_pos.set(40)

    def home_axis(self):
        default_pos = self.default_pos.get()
        print(f"Homing axis to default position: {default_pos} mm")
        self.zaber.axis.move_absolute(default_pos, Units.LENGTH_MILLIMETRES)
        self.position.set(default_pos)

    def park_axis(self):
        if not self.zaber.axis.is_parked():
            print("Parking axis")
            self.zaber.axis.park()
        else:
            print("Unparking axis")
            self.zaber.axis.unpark()

    # small helpers that mirror main_window
    def _info_icon(self, parent, tooltip_text):
        lbl = ttk.Label(parent, text="ⓘ", style="Info.TLabel", cursor="hand2")
        self._attach_tooltip(lbl, tooltip_text)
        return lbl

    def _attach_tooltip(self, widget, text):
        tooltip = tk.Toplevel(widget)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tk.Label(tooltip, text=text, bg="#fff7e6", fg="#3b3f47",
                 padx=10, pady=6, relief="solid", borderwidth=1,
                 wraplength=320, justify="left",
                 font=("Helvetica", 9)).pack()

        def show(_):
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 22
            tooltip.geometry(f"+{x}+{y}")
            tooltip.deiconify()

        def hide(_):
            tooltip.withdraw()

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _labeled(self, parent, text, tooltip):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(anchor="w", fill="x")
        ttk.Label(row, text=text, style="FieldLabel.TLabel").pack(side="left")
        if tooltip:
            self._info_icon(row, tooltip).pack(side="left", padx=(6, 0))
        return row

    def _position_field(self, parent, var, label_text, tooltip):
        # one row: label + entry + 'mm' suffix, height matched with mm² in main page
        self._labeled(parent, label_text, tooltip)
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 12))
        entry = ttk.Entry(row, textvariable=var, style="Input.TEntry", cursor="xterm")
        entry.pack(side="left", fill="x", expand=True)
        ttk.Label(row, text="mm", style="UnitSuffix.TLabel").pack(side="left", padx=(6, 0))
        self.widgets.append(entry)
        return entry

    # nav row — plain inline buttons matching the main page
    def navbar(self, parent):
        def back_to_main():
            self.window.destroy()
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 12))
        ttk.Button(row, text='Main Stage', style="Nav.TButton",
                   command=back_to_main).pack(side="left", padx=(0, 6))
        ttk.Button(row, text='Control Panel', style="Nav.TButton",
                   state=tk.DISABLED).pack(side="left")

    def _create_widgets(self):
        # scrollable shell — no visible scrollbar; trackpad scrolling handled by install_mousewheel
        canvas = tk.Canvas(self.window, bg="#eef2f7", highlightthickness=0, bd=0,
                           yscrollincrement=8)
        canvas.pack(side="left", fill="both", expand=True)

        scroll_frame = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def on_frame_configure(_):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        scroll_frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        # remember canvas; mousewheel is installed at the end of widget construction
        self._canvas = canvas

        def on_destroy(event):
            if event.widget is self.window:
                try:
                    self.main_window.restore_main_mousewheel()
                except Exception:
                    pass
        self.window.bind("<Destroy>", on_destroy)

        container = ttk.Frame(scroll_frame, padding=(20, 14, 20, 14))
        container.pack(fill="both", expand=True)

        # nav buttons
        self.navbar(container)

        # title row
        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Zaber Control Panel",
                  style="Title.TLabel").pack(anchor="w")

        # connection card
        conn_card = tk.Frame(container, bg="#ffffff",
                             highlightthickness=1,
                             highlightbackground="#dde2eb",
                             highlightcolor="#dde2eb")
        conn_card.pack(fill="x", pady=(0, 14))
        conn_inner = ttk.Frame(conn_card, padding=(20, 18, 20, 18),
                               style="Card.TFrame")
        conn_inner.pack(fill="x")
        ttk.Label(conn_inner, text="Connection",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 10))

        self._labeled(conn_inner, "Zaber COM Port",
                      "Serial port used to communicate with the Zaber actuator. "
                      "Select a port to enable the controls below.")
        comport_row = ttk.Frame(conn_inner, style="Card.TFrame")
        comport_row.pack(fill="x", pady=(6, 4))
        ports = [p.device for p in serial.tools.list_ports.comports()]
        comport_combo = ttk.Combobox(comport_row,
                                     values=ports,
                                     state='readonly',
                                     textvariable=self.zaber_comport,
                                     style="Input.TCombobox",
                                     cursor="arrow")
        if not self.zaber_comport.get():
            comport_combo.set('Select Comport')
        comport_combo.pack(fill="x")

        def _clear_highlight(event):
            try:
                event.widget.selection_clear()
                event.widget.master.focus_set()
            except tk.TclError:
                pass
        comport_combo.bind("<<ComboboxSelected>>", _clear_highlight)
        ttk.Label(conn_inner,
                  text="Connect a port to unlock position controls.",
                  style="Caption.TLabel").pack(anchor="w", pady=(2, 0))

        # stage position card
        pos_card = tk.Frame(container, bg="#ffffff",
                            highlightthickness=1,
                            highlightbackground="#dde2eb",
                            highlightcolor="#dde2eb")
        pos_card.pack(fill="x", pady=(0, 14))
        pos_inner = ttk.Frame(pos_card, padding=(20, 18, 20, 18),
                              style="Card.TFrame")
        pos_inner.pack(fill="x")
        ttk.Label(pos_inner, text="Stage Position",
                  style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 10))

        # two-column layout: slider/up-down on the left, position fields on the right
        two_col = ttk.Frame(pos_inner, style="Card.TFrame")
        two_col.pack(fill="x")
        two_col.grid_columnconfigure(0, weight=1, uniform="cp")
        two_col.grid_columnconfigure(1, weight=1, uniform="cp")

        left_col = ttk.Frame(two_col, style="Card.TFrame")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self._build_slider(left_col)

        right_col = ttk.Frame(two_col, style="Card.TFrame")
        right_col.grid(row=0, column=1, sticky="nsew")
        self._position_field(right_col, self.position,
                             "Current Position",
                             "Live position of the Zaber actuator in millimetres.")
        self._position_field(right_col, self.min_pos,
                             "Min Position",
                             "Lower travel bound. Slider and entries clamp to this value.")
        self._position_field(right_col, self.max_pos,
                             "Max Position",
                             "Upper travel bound. Slider and entries clamp to this value.")
        self._position_field(right_col, self.default_pos,
                             "Default (Home) Position",
                             "Position returned to when you click Home.")

        # action row lives inside the stage position card, split 50/50 across the row
        actions = ttk.Frame(pos_inner, style="Card.TFrame")
        actions.pack(fill="x", pady=(12, 0))

        home_btn = ttk.Button(actions, text="Home", command=self.home_axis,
                              style="Outline.TButton")
        home_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        park_btn = ttk.Button(actions, text="Park", command=self.park_axis,
                              style="Outline.TButton")
        park_btn.pack(side="left", fill="x", expand=True, padx=(6, 6))

        calibrate_btn = ttk.Button(actions, text="Calibrate",
                                   style="Outline.TButton")
        calibrate_btn.pack(side="left", fill="x", expand=True, padx=(6, 6))

        save_btn = ttk.Button(actions, text="Save Inputs",
                              command=self.save_inputs, style="Primary.TButton")
        save_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.widgets.extend([home_btn, park_btn, calibrate_btn, save_btn])

        # wire mousewheel scrolling now that every widget under the canvas exists
        self.main_window.install_mousewheel(self._canvas)

    def _build_slider(self, parent):
        # vertical slider + up/down increment buttons
        ttk.Label(parent, text="Position Slider",
                  style="FieldLabel.TLabel").pack(anchor="w")

        body = ttk.Frame(parent, style="Card.TFrame")
        body.pack(anchor="w", pady=(6, 0))

        slider = ttk.Scale(body, variable=self.position, orient=tk.VERTICAL,
                           from_=self.min_pos.get(), to=self.max_pos.get(),
                           length=180)
        slider.pack(side="left", padx=(0, 12))
        self.widgets.append(slider)

        # up/down stack
        btn_col = ttk.Frame(body, style="Card.TFrame")
        btn_col.pack(side="left")
        ttk.Label(btn_col, text="Increment", style="Caption.TLabel").pack(pady=(0, 4))

        def up():
            if self.position.get() > self.min_pos.get():
                self.position.set(self.position.get() - 1)

        def down():
            if self.position.get() < self.max_pos.get():
                self.position.set(self.position.get() + 1)

        up_btn = ttk.Button(btn_col, text="▲", command=up,
                            style="Outline.TButton", width=4)
        up_btn.pack(pady=(0, 4))
        down_btn = ttk.Button(btn_col, text="▼", command=down,
                              style="Outline.TButton", width=4)
        down_btn.pack()

        self.widgets.extend([up_btn, down_btn])
