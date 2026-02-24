import tkinter as tk
from tkinter import ttk
import serial.tools.list_ports
"""
Skeleton framework for an analysis window that would allow the user to view
any related analysis files without having to open a file manager
Currently not being used.
"""

class ControlWindow(tk.Frame):
    """ Separate window for looking at control panel"""

    def __init__(self, root, main_window):
        super().__init__(root)
        self.root = root
        self.main_window = main_window
        self.bg = "#cce7ff"
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
        self.default_pos = tk.IntVar(value=17)
        self.position = tk.IntVar(value=0)
        self.min_pos = tk.IntVar(value=0) # we should trace this value because min < max
        self.max_pos = tk.IntVar(value=50) # we should trace this value because max > min
        self.speed = tk.IntVar(value=1) # we should trace this value because it shouldnt go too fast
        self.zaber_comport = tk.StringVar(value="")

        #self.window.grid_columnconfigure(0, weight=1)
        #self.root.grid_columnconfigure(1, weight=1)
        self.navbar()
        self.remote()
        self.input_fields_pos()
        self.input_fields_other()
        self.create_buttons()

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
    
    def remote(self):
        # Makes the zaber stage using a slider and buttons
        rem = tk.Frame(self.window, bg=self.bg)
        rem.grid(sticky='w', row=1, column=0, rowspan=4, columnspan=1)
        self._create_slider(rem)
        self._create_updown_btns(rem)

    def _create_slider(self, parent):
        """
        Vertical slider to control positioning
        """
        min = self.min_pos.get()
        max = self.max_pos.get()
        slider = tk.Scale(parent, variable=self.position, from_=min, to_=max, orient=tk.VERTICAL, length=150)

        slider_label = tk.Label(parent, text="Position")
        slider_label.grid(sticky='ew', row=1, column=0, padx=10)
        slider.grid(sticky='ew', row=2, rowspan=6, column=0, padx=10)
    
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
        frame.grid(sticky='ew', row=1, column=1, rowspan=5, columnspan=4)
    
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
        min_pos_label = tk.Label(frame, text="Max Position")
        min_pos_input = tk.Entry(frame, textvariable=self.max_pos, width=10)
        max_pos_units = tk.Label(frame, text="mm")

        min_pos_label.grid(sticky='ew', row=2, column=0)
        min_pos_input.grid(sticky='ew', row=2, column=1)
        max_pos_units.grid(sticky='ew', row=2, column=2)

        # Default position
        default_pos_label = tk.Label(frame, text="Default Position")
        default_pos_input = tk.Entry(frame, textvariable=self.default_pos, width=10)
        default_pos_units = tk.Label(frame, text="mm")

        default_pos_label.grid(sticky='ew', row=3, column=0, pady=25)
        default_pos_input.grid(sticky='ew', row=3, column=1)
        default_pos_units.grid(sticky='ew', row=3, column=2)

    
    def input_fields_other(self):
        """
        Frame that holds all other input fields not related to positioning
        Speed
        Acceleration
        Comport
        """
        frame = tk.Frame(self.window, bg=self.bg)
        frame.grid(sticky='ew', row=1, column=6, rowspan=5, columnspan=3)

        # Speed
        speed_pos_label = tk.Label(frame, text="Speed")
        speed_pos_input = tk.Entry(frame, textvariable=self.speed, width=10)
        speed_pos_units = tk.Label(frame, text="mm/s")

        speed_pos_label.grid(sticky='ew', row=0, column=0)
        speed_pos_input.grid(sticky='ew', row=0, column=1)
        speed_pos_units.grid(sticky='ew', row=0, column=2)

        self._create_comport_selection(frame)

    def _create_comport_selection(self, parent):
        """Selection box for zaber comports"""
        zaber_label = tk.Label(parent, text="Zaber Comport:")
        zaber_combobox = ttk.Combobox(parent, 
                                       values=[port.device for port in serial.tools.list_ports.comports()],
                                       state='readonly', textvariable=self.zaber_comport, width=15)
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
        frame.grid(sticky='ew', row=7, column=0, columnspan=3, pady=25)
        
        # Homing
        home_btn = tk.Button(frame, text="Home", width=10)
        home_btn.grid(sticky='w', row=0, column=0, padx=10)

        # Parking
        # TODO: This will need to have a callback function *Pause button flashbacks*
        park_btn = tk.Button(frame, text="Park", width=10)
        park_btn.grid(sticky='w', row=0, column=1, padx=25)

        # Calibrate
        # TODO: this will need to have a warning attached since its part of a larger function
        calibrate_btn = tk.Button(frame, text="Calibrate", width=10)
        calibrate_btn.grid(sticky='w', row=0, column=2, padx=25)




    


