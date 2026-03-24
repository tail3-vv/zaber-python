import tkinter as tk
from tkinter import ttk
import serial.tools.list_ports
from zaber_motion import Units
from zaber_cli import ZaberCLI
"""
Skeleton framework for an analysis window that would allow the user to view
any related analysis files without having to open a file manager
Currently not being used.
"""

class ControlWindow(tk.Frame):
    """ Separate window for looking at control panel"""

    def __init__(self, root, main_window, zaber):
        super().__init__(root)
        self.root = root
        self.main_window = main_window
        self.zaber = zaber # to interact with the zaber CLI
        self.bg = None# "#cce7ff"
        # Create an overlay Frame that covers the entire root window.
        # Use place with relwidth/relheight so it always fills the window.
        self.window = tk.Frame(self.root, bg=self.bg)
        self.window.place(relx=0, rely=0, relwidth=1, relheight=1)
        # Ensure overlay is above other widgets
        try:
            self.window.lift()
        except Exception:
            pass
        # Allow grid-managed children inside this overlay to expand
        for i in range(8):
            self.window.grid_columnconfigure(i, weight=1)
        
        # TODO: Set the default to Zaber current position
        self.zaber = ZaberCLI()
        self.default_pos = tk.IntVar(value=17)
        self.position = tk.IntVar(value=17)
        self.min_pos = tk.IntVar(value=17) # we should trace this value because min < max
        self.max_pos = tk.IntVar(value=40) # we should trace this value because max > min
        self.speed = tk.DoubleVar(value=0.5) # we should trace this value because it shouldnt go too fast
        self.zaber_comport = tk.StringVar(value="")
        self.widgets = [] # hold all widgets in a list (to be enabled when zaber is connected)

        #self.window.grid_columnconfigure(0, weight=1)
        #self.root.grid_columnconfigure(1, weight=1)
        self.navbar()
        self.header()
        self.remote()
        self.input_fields_pos()
        self.input_fields_other()
        self.create_buttons()
        self.zaber_comport.trace('w', self.trace_comport)

        separator = ttk.Separator(self.window)
        # separator.grid(sticky="w", row=4, column=1, pady=10)
        separator.place(x=0, y=350, relwidth=1)

        # Initially disable all widgets until user has picked a zaber comport
        for w in self.widgets:
            w.config(state=tk.DISABLED)
    
    def trace_comport(self, *args):
        
        # if comport is the valid zaber comport
        # then here we allow all widgets
        for w in self.widgets:
            w.config(state=tk.NORMAL)
        print(f"Selected Zaber Comport: {self.zaber_comport.get()}")
        self.zaber.connect(self.zaber_comport.get())
        pos = self.zaber.axis.get_position()
        pos = (pos* 0.04765) / 1000 # convert from microsteps to mm
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

        # print(f"Speed changed to: {self.speed.get()}")
        # speed = self.speed.get()
        # if speed < 0.1:
        #     speed = 0.1
        #     self.speed.set(speed)
        # elif speed > 2:
        #     speed = 2
        #     self.speed.set(speed)
        # self.zaber.axis.move_velocity(speed, Units.VELOCITY_MILLIMETRES_PER_SECOND)

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

    def navbar(self):
        def back_to_main():
            #goes back to main window by closing this frame
            self.window.destroy()

        navbar = tk.Frame(self.window, bg="lightblue", height=32, bd=3, relief=tk.RIDGE)
        # Make the navbar expand horizontally across the overlay
        navbar.grid(sticky='ew', row=0, column=0, columnspan=8, rowspan=1)

        for i in range(50):
            navbar.columnconfigure(i, weight=1)

        # Navigation buttons
        main_btn = tk.Button(navbar, text='Main Stage', command=back_to_main, width=10)
        control_btn = tk.Button(navbar, text='Control Panel', state=tk.DISABLED, width=10)

        # Layout
        main_btn.grid(sticky='w', row=0, column=0, padx=10)
        control_btn.grid(sticky='w', row=0, column=1)

    def header(self):
        """
        Text header label with instructions for this window
        """
        bg_color= None#'white'
        header_frame = tk.Frame(self.window, bg=bg_color)
        header_frame.grid(sticky='ew', row=1, column=0, columnspan=8, rowspan=3, pady=10)
        title_label = tk.Label(header_frame, text="Zaber Control Panel", font=("Helvetica", 16), bg=bg_color)
        subtext_label = tk.Label(header_frame, text="Specify a comport to begin controlling the stage.", bg=bg_color)
        
        header_frame.columnconfigure(0, weight=1)
        title_label.grid(sticky='w', row=0, column=0, padx=10)
        subtext_label.grid(sticky='w', row=1, column=0, padx=10)

        # create a separator
        separator = ttk.Separator(header_frame)
        separator.grid(sticky="ew", row=2, column=0, columnspan=8, pady=25)
        #separator.place(x=0, y=y_value, relwidth=1)
    
    def remote(self):
        # Makes the zaber stage using a slider and buttons
        rem = tk.Frame(self.window, bg=self.bg)
        rem.grid(sticky='w', row=3, column=0, rowspan=4, columnspan=1, pady=110)

        self._create_slider(rem)
        self._create_updown_btns(rem)

    def _create_slider(self, parent):
        """
        Vertical slider to control positioning
        """
        min = self.min_pos.get()
        max = self.max_pos.get()
        slider = tk.Scale(parent, variable=self.position, from_=min, to_=max, orient=tk.VERTICAL, length=150)
        self.widgets.append(slider)

        slider_label = tk.Label(parent, text="Position")
        slider_label.grid(sticky='ew', row=0, column=0, padx=12)
        slider.grid(sticky='ew', row=1, rowspan=6, column=0, padx=10, pady=10)
    
    def _create_updown_btns(self, parent):
        """
        Up and down buttons to control positioning incrementally
        """
        def up():
            p = self.position 
            min_ = self.min_pos
            if p.get() > min_.get():
                p.set(p.get() - 1)
        def down():
            p = self.position
            max_ = self.max_pos
            if p.get() < max_.get():
                p.set(p.get() + 1)
        
        btn_frame = tk.Frame(parent)
        btn_frame.grid(row=2,column=1, pady=30, padx=17)
        up_btn = tk.Button(btn_frame, command=up, text="^", width=10)
        down_btn = tk.Button(btn_frame, command=down, text="⌄", width=10)
        btn_label = tk.Label(btn_frame, text="Increment Position")
        
        self.widgets.extend([up_btn, down_btn])

        btn_label.grid(sticky='ew', row=1, column=1)
        up_btn.grid(sticky='ew', row=2, column=1)
        down_btn.grid(sticky='ew', row=3, column=1)

    def input_fields_pos(self):
        """
        Frame that holds all the input fields such as 
        Current position
        Min/Max Position
        Default Position
        """
        frame = tk.Frame(self.window, bg=self.bg)
        frame.grid(sticky='ew', row=3, column=1, rowspan=5, columnspan=4)
    
        # Current position
        curr_pos_label = tk.Label(frame, text="Current Position")
        curr_pos_input = tk.Entry(frame, textvariable=self.position, width=10)
        curr_pos_units = tk.Label(frame, text="mm")

        curr_pos_label.grid(sticky='ew', row=0, column=0)
        curr_pos_input.grid(sticky='ew', row=0, column=1)
        curr_pos_units.grid(sticky='ew', row=0, column=2)

        # Min position
        min_pos_label = tk.Label(frame, text="Min Position")
        min_pos_input = tk.Entry(frame, textvariable=self.min_pos, width=10)
        min_pos_units = tk.Label(frame, text="mm")

        min_pos_label.grid(sticky='ew', row=1, column=0, pady=25)
        min_pos_input.grid(sticky='ew', row=1, column=1)
        min_pos_units.grid(sticky='ew', row=1, column=2)

        # Max position
        max_pos_label = tk.Label(frame, text="Max Position")
        max_pos_input = tk.Entry(frame, textvariable=self.max_pos, width=10)
        max_pos_units = tk.Label(frame, text="mm")

        max_pos_label.grid(sticky='ew', row=2, column=0)
        max_pos_input.grid(sticky='ew', row=2, column=1)
        max_pos_units.grid(sticky='ew', row=2, column=2)

        # Default position
        default_pos_label = tk.Label(frame, text="Default Position")
        default_pos_input = tk.Entry(frame, textvariable=self.default_pos, width=10)
        default_pos_units = tk.Label(frame, text="mm")

        default_pos_label.grid(sticky='ew', row=3, column=0, pady=25)
        default_pos_input.grid(sticky='ew', row=3, column=1)
        default_pos_units.grid(sticky='ew', row=3, column=2)

        self.widgets.extend([curr_pos_input, min_pos_input, max_pos_input,
                             default_pos_input])

    
    def input_fields_other(self):
        """
        Frame that holds all other input fields not related to positioning
        Speed
        Acceleration
        Comport
        """
        frame = tk.Frame(self.window, bg=self.bg)
        frame.grid(sticky='ew', row=3, column=6, rowspan=5, columnspan=3)

        # Speed
        # speed_pos_label = tk.Label(frame, text="Speed")
        # speed_pos_input = tk.Entry(frame, textvariable=self.speed, width=10)
        # speed_pos_units = tk.Label(frame, text="mm/s")

        # speed_pos_label.grid(sticky='ew', row=0, column=0)
        # speed_pos_input.grid(sticky='ew', row=0, column=1)
        # speed_pos_units.grid(sticky='ew', row=0, column=2)

        self._create_comport_selection(frame)
        # self.widgets.extend([speed_pos_input])

    def _create_comport_selection(self, parent):
        """Selection box for zaber comports"""
        zaber_label = tk.Label(parent, text="Zaber Comport:")
        zaber_combobox = ttk.Combobox(parent, 
                                       values=[port.device for port in serial.tools.list_ports.comports()],
                                       state='readonly', textvariable=self.zaber_comport, width=15)
        # [port.device for port in serial.tools.list_ports.comports()]
        zaber_combobox.set('Select Comport')
        zaber_label.grid(sticky='w', row=1, column=0, pady=25)
        zaber_combobox.grid(sticky='w', row=1, column=1)

    def create_buttons(self):
        """
        Create buttons for various zaber functions such as:
        Homing (goes back to default position)
        Park/Unpark (Stalls axis)
        Calibrate (runs calibration script)

        Reset axis/defaults
        """
        frame = tk.Frame(self.window, bg=self.bg)
        frame.grid(sticky='ew', row=6, column=0, columnspan=8)
        
        # Homing
        home_btn = tk.Button(frame, text="Home", command=self.home_axis, width=10)
        home_btn.grid(sticky='w', row=0, column=0, padx=10)

        # Parking
        # TODO: This will need to have a callback function *Pause button flashbacks*
        park_btn = tk.Button(frame, text="Park", command=self.park_axis, width=10)
        park_btn.grid(sticky='w', row=0, column=1, padx=25)

        # Calibrate
        # TODO: this will need to have a warning attached since its part of a larger function
        calibrate_btn = tk.Button(frame, text="Calibrate", width=10)
        calibrate_btn.grid(sticky='w', row=0, column=2, padx=25)

        # Save inputs 
        save_btn = tk.Button(frame, text="Save Inputs", command=self.save_inputs, width=10)
        save_btn.grid(sticky='w', row=0, column=3, padx=25)


        self.widgets.extend([home_btn, park_btn, calibrate_btn, save_btn])




    


