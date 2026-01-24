import tkinter as tk
from tkinter import Tk
from tkinter import ttk
from tkinter import filedialog as fd
import serial.tools.list_ports
from run_test import run_tests, test_funct
class mainWindow():
    def __init__(self):
        self.root = Tk(screenName=None, baseName=None, className='Tk', useTk=1)
        self.root.title("Zaber Control Stage")
        self.root.geometry("625x375")
        self.root.resizable(False, False)

        """
        These are the initial test settings
        """
        # Initially these are empty strings
        self.saved_path = tk.StringVar()
        self.sensor_id = tk.StringVar()

        # Initially these are set to 0 unless specified
        self.is_create_files = tk.IntVar() # this is boolean
        self.n_runs = tk.IntVar(value=3)
        self.is_pause_between_runs = tk.IntVar(value=1) # this is boolean
        self.is_test_started = tk.IntVar(value=0) # this is boolean

        # Comports have default values
        self.zaber_comport = tk.StringVar(value="COM3")
        self.futek_comport = tk.StringVar(value="COM4")

        """
        These variables control the state of the test ie pauses, stops, recalibrations
        """
        self.textbox = None
        self.toggle_pause = tk.IntVar(value=0) # this is boolean, paused=1, not paused=0

    def display_updates(self):
        """ Display updates about current run progress """
        textbox = tk.Text(self.root, 
                          width=61,
                          height=5,
                          borderwidth=5,
                          relief='groove'
                          )
        textbox.grid(sticky='w', row=0, column=0, rowspan=1, 
                     columnspan=3, padx=10, pady=20)
        textbox.config(state=tk.DISABLED)
        self.textbox = textbox
    
    def update_textbox(self, text):
        self.textbox.config(state=tk.NORMAL)
        self.textbox.insert(tk.END, f"{text}\n")
        self.textbox.config( state=tk.DISABLED)

    # *args is necessary for the trace() funct
    def trace_path(self, *args):
        """ Trace changes to the saved_path variable """
        path = self.saved_path.get()
        sensor = self.sensor_id.get()
        checkbox = self.is_create_files.get()
        testStarted = self.is_test_started.get()
        n_runs = self.n_runs.get()
        if testStarted:
            self.update_textbox("Run 1 started")
            state = test_funct(n_runs, path, sensor)

    def select_folder(self):
        """ Prompt user for save folder """
        def open_folder():
            """ Helper function that takes user to native file selector """
            file_path = fd.askdirectory()
            
            if file_path:
                self.saved_path.set(file_path)

        # Create an open file button
        open_button = tk.Button(self.root, text='Browse folders...',
                                command=open_folder)

        # Widget Labels
        label = tk.Label(self.root, text="Save Folder: ")
        folder_entry = tk.Entry(self.root, textvariable=self.saved_path, width=50)

        # Widget positions
        label.grid(sticky='w', row=1, column=0, padx=10,pady=10)
        folder_entry.grid(sticky='w', row=1, column=1, pady=10)
        open_button.grid(sticky='w', row=1, column=2, padx=10,pady=10)

    def enter_sensor_id(self):
        """ Prompt user for sensor id """
        # Widget Labels
        label = tk.Label(self.root, text="Sensor Id#: ")
        sensor_entry = tk.Entry(self.root, textvariable=self.sensor_id, width=50)

        # Widget positions
        label.grid(sticky='w', row=2, column=0, padx=10,pady=10)
        sensor_entry.grid(sticky='w', row=2, column=1, pady=10)
    
    def add_separator(self, y_value, window):
        """Adds seperator line to window"""
        separator = ttk.Separator(window)
        # separator.grid(sticky="w", row=4, column=1, pady=10)
        separator.place(x=0, y=y_value, relwidth=1)
    
    def create_files_checkbox(self):
        """ Checkbox to create folders if the do not exist on user's filepath """
        checkbox = tk.Checkbutton(self.root, text="Create folders if they do not exist",
                                  variable=self.is_create_files, command=self.is_create_files.get())
        checkbox.grid(sticky="w", row=4, column=1, pady=40)

    def begin_test_btn(self):
        """ Opens dialog to verify settings before actually beginning tests """
        btn = tk.Button(self.root, text="Begin Test", command=self.open_settings)
        btn.grid(sticky="w", row=6, column=3)
    
    def toggle_pause_btn(self):
        """
        Pauses current run
        Checks if there is a test occuring before pausing
        If test is already paused, text changes to unpause test
        """
        btn = tk.Button(self.root, text="Pause Run", command=print("paused"))
        btn.grid(sticky="w", row=6, column=2)

    def open_settings(self):
        """
        Opens a secondary window to verify settings before beginning tests
        """
        # Create a new top-level window
        settings = tk.Toplevel(self.root)
        settings.title("Verify Settings")
        settings.geometry("300x400") 
        settings.resizable(False, False)
        # Disable interaction with main window
        settings.grab_set()

        # Heading
        heading_frame = tk.Frame(settings, width=300, height=50)
        heading_frame.grid(sticky='w', row=1, pady=10)
        heading = tk.Label(heading_frame, 
                           text="Verify settings before beginning tests. \n" \
                           "You cannot move on until all settings are filled in.")
        heading.pack(padx=10, pady=20)

        def enter_num_runs():
            """ 
            Prompt user to enter number of runs during testing 
            Default: 3 runs
            """
            label = tk.Label(settings, text="Number of Runs:")
            runs_entry = tk.Spinbox(settings, from_=1, to=10, textvariable=self.n_runs, width=10)

            # Widget positions
            label.grid(sticky='w', row=2, column=0, padx=10,pady=10)
            runs_entry.grid(sticky='w', row=2, column=0, padx=125, pady=10)

        def pause_between_checkbox():
            """ 
            Checkbox whether the user wants to pause between runs 
            Default: Checked
            """
            checkbox = tk.Checkbutton(settings, text="Pause between Runs?",
                            variable=self.is_pause_between_runs, command=self.is_pause_between_runs.get())
            checkbox.grid(sticky="w", row=3, column=0, padx=10)

        def select_comports():
            """Selection box for zaber and futek comports"""
            def zaber_select(event):
                """When a zaber comport is selected the futek comport gets enabled"""
                # Enable futek combobox
                futek_combobox.config(state=tk.NORMAL)

            zaber_label = tk.Label(settings, text="Zaber Comport:")
            zaber_combobox = ttk.Combobox(settings, values=[port.device for port in serial.tools.list_ports.comports()],
                                            state='readonly', textvariable=self.zaber_comport)
            zaber_combobox.set('Select Comport')

            zaber_label.grid(sticky='w', row=4, column=0, padx=10,pady=10)
            zaber_combobox.grid(sticky='w', row=4, column=0, padx=125, pady=10)
            
            zaber_combobox.bind("<<ComboboxSelected>>", zaber_select)

            # Futek
            futek_label = tk.Label(settings, text="Futek Comport:")
            futek_combobox = ttk.Combobox(settings, values=[port.device for port in serial.tools.list_ports.comports()],
                                            state=tk.DISABLED, textvariable=self.futek_comport)
            futek_combobox.set('Select Comport')

            futek_label.grid(sticky='w', row=5, column=0, padx=10,pady=10)
            futek_combobox.grid(sticky='w', row=5, column=0, padx=125, pady=10)

        def begin_test_btn():
            """ Opens dialog to verify settings before actually beginning tests """
            def btn_clicked():
                settings.grab_release()
                settings.withdraw()
                self.is_test_started.set(1)
            btn = tk.Button(settings, text="Begin Test", command=btn_clicked)
            btn.grid(sticky="w", row=6, column=0, padx=215, pady=115)
            
                

        self.add_separator(y_value=90, window=settings)
        enter_num_runs()
        pause_between_checkbox()
        select_comports()
        self.add_separator(y_value=250, window=settings)
        begin_test_btn()

def run():
    main = mainWindow()
    main.display_updates()
    main.select_folder()
    main.enter_sensor_id()
    main.add_separator(y_value=310, window=main.root) # about every 50 px is a row
    main.create_files_checkbox()
    main.begin_test_btn()
    main.toggle_pause_btn()

    main.is_test_started.trace('w', main.trace_path)

    main.root.mainloop()

run()