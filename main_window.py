import cmd
import tkinter as tk
from tkinter import Tk
from tkinter import ttk
from tkinter import filedialog as fd
from tkinter import scrolledtext
import numpy as np
import subprocess
import sys
import signal
import os
import time
import xlsxwriter
import math
from time import sleep
from pathlib import Path
from datetime import datetime
from zaber_cli import ZaberCLI
# from futek_cli import FUTEKDeviceCLI
from zaber_motion import Units
from settings_window import SettingsWindow
from shear_window import ShearWindow
from control_window import ControlWindow
from em_analysis import EMAnalysis
from shear_analysis import ShearAnalysis

"""
File where mainloop is executed.
Holds infrastructure to execute all tests
Implementation for EM testing is here, shear testing implementation is in shear_window
EM testing requires too many dependent variables to be kept in a separate file
"""
class MainWindow:
    def __init__(self):
        self.root = Tk(screenName=None, baseName=None, className='Tk', useTk=1)
        self.root.title("Zaber Control Stage")
        self.root.geometry("650x425")
        self.root.resizable(False, False)

        # Configure grid weights so widgets expand with window
        for i in range(8):
            self.root.grid_columnconfigure(i, weight=1)

        """
        These are the initial test settings
        """
        # Initially these are empty strings
        self.saved_path = tk.StringVar()
        self.sensor_id = tk.StringVar()
        self.sensor_type = tk.StringVar(value="Standard") # Standard, channel order is 1-8

        # Initially these are set to 0 unless specified
        self.is_create_files = tk.BooleanVar(value=1) # this is boolean
        self.is_pause_between_runs = tk.BooleanVar(value=1) # this is boolean
        self.is_test_started = tk.BooleanVar(value=0) # this is boolean

        # Track the current run
        self.n_runs = tk.IntVar(value=3)
        self.current_run = tk.IntVar(value=1)
        
        # Comports have default values
        self.zaber_comport = tk.StringVar(value="COM3")

        # EM, Shear etc.
        self.test_type = tk.StringVar(value="EM")

        # surface area of eco block ie 325mm2, 50.27, etc.
        self.surface_area = tk.StringVar(value="325mm2")

        """
        These variables control the state of the test ie pauses, stops, recalibrations
        """
        self.textbox = None
        self.pause_btn = None
        self.toggle_pause = tk.BooleanVar(value=0) # this is boolean, paused=1, not paused=0
        self.is_warning_cancel = tk.BooleanVar(value=0) # this is for pause warning currently during EM test
        self.widgets = [] # when testing starts, these widgets will all get disabled

        self._create_widgets()

        # On close of window behavior
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)


    def display_updates(self):
        """ Display updates about current run progress """
        textbox = scrolledtext.ScrolledText(self.root, 
                          width=61,
                          height=5,
                          borderwidth=5,
                          relief='groove'
                          )
        textbox.grid(sticky='w', row=1, column=0, rowspan=1, 
                     columnspan=3, padx=10, pady=20)
        textbox.config(state=tk.DISABLED)
        self.textbox = textbox
    
    def update_textbox(self, text):
        """ Helper function to change the text in the updates textbox """
        self.textbox.config(state=tk.NORMAL)
        self.textbox.insert(tk.END, f"{text}\n")
        self.textbox.config( state=tk.DISABLED)

    # *args is necessary for the trace() funct
    # TODO: Possibly make separate trace functions for pause run and continuous run
    def trace_test(self, *args):
        """ Trace changes to the saved_path variable """
        test_start = self.is_test_started.get()
        test_type = self.test_type.get()
        if test_start:
            # Disable widgets
            for w in self.widgets:
                    w.config(state=tk.DISABLED)

            if test_type == "EM":
                self.pause_btn.config(state=tk.NORMAL)
                self._EM_test()
            elif  test_type == "Shear":
                self.pause_btn.config(state=tk.DISABLED)
                self._shear_test()
        else:
            # Reenable widgets
            for w in self.widgets:
                w.config(state=tk.NORMAL)

    def trace_pause(self, *args):
        """ Trace changes to the toggle_pause variable to resume testing when unpaused """
        self.update_pause_btn() # Updates pause button text based on toggle state

    def _shear_test(self):
        """"""
        shear_window = ShearWindow(self.root, self)

    def _EM_test(self):
        """ Helper function to continue test if conditions are met """
        if not (self.is_test_started.get() and self.toggle_pause.get() == 0):
            return
        
        n_runs = self.n_runs.get()
        current_run = self.current_run.get()
        
        # Run Test function and update textbox according to progress
        self.update_textbox(f"Beginning run {current_run}")
        # state = self.test_funct(n_runs, current_run, self.saved_path.get(), 
        #                         self.sensor_id.get(), self.zaber_comport.get())
        # state = self.run_tests(n_runs, current_run, self.zaber_comport.get())
        state = self.run_triangle_test(current_run, self.zaber_comport.get())

        # Check if run was paused or completed
        is_paused = current_run == state
        self.update_textbox(f"Run {current_run} was paused" if is_paused 
                           else f"Run {current_run} completed")
        
        # Handle test completion or continue to next run
        if current_run == n_runs and not is_paused:
            self.update_textbox(f"All runs complete")
            self._end_testing()
        else:
            self.current_run.set(state)
            if state <= n_runs:
                self.toggle_pause.set(1)
                self.update_pause_btn()
    
    def _end_testing(self):
        """ End Testing and reset variables """
        self.testing_complete()
        self.is_test_started.set(0)
        self.current_run.set(1)
        #self.saved_path.set("")
        #self.sensor_id.set("")

    """
    GUI Widgets that remain mostly the same during testing
    """
    def navbar(self):
        def open_control():
            zaber = ZaberCLI()
            control = ControlWindow(self.root, self, zaber)
        navbar = tk.Frame(self.root, bg="lightblue", width=700, height=32, bd=3, relief=tk.RIDGE)
        navbar.grid(sticky='ew', row=0, column=0, columnspan=8, rowspan=1)
        #self.root.grid_rowconfigure(0, weight=1)
        for i in range(50):
            navbar.columnconfigure(i, weight=1)
        # Navigation buttons
        main_btn = tk.Button(navbar, text='Main Stage', width=10, state=tk.DISABLED)
        control_btn = tk.Button(navbar, text='Control Panel', command=open_control, width=10)

        # Layout
        main_btn.grid(sticky='w', row=0, column=0, padx=10)
        control_btn.grid(sticky='w', row=0, column=1)

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
        label.grid(sticky='w', row=2, column=0, padx=10,pady=10)
        folder_entry.grid(sticky='w', row=2, column=1, pady=10)
        open_button.grid(sticky='w', row=2, column=2, padx=10,pady=10)

        # Add Widgets to list
        self.widgets.append(folder_entry)
        self.widgets.append(open_button)

    def enter_sensor_id(self):
        """ Prompt user for sensor id """
        # Widget Labels
        label = tk.Label(self.root, text="Sensor Id#: ")
        sensor_entry = tk.Entry(self.root, textvariable=self.sensor_id, width=50)

        # Widget positions
        label.grid(sticky='w', row=3, column=0, padx=10,pady=10)
        sensor_entry.grid(sticky='w', row=3, column=1, pady=10)

        # Add Widgets to list
        self.widgets.append(sensor_entry)
    
    def select_sensor_type(self):
        """ Prompt user for sensor type """
        # Widget Labels
        label = tk.Label(self.root, text="Sensor Type: ")
        sensor_entry = ttk.Combobox(self.root, textvariable=self.sensor_type, 
                                   values=["Standard", "Inverted"], width=10)

        # Widget positions
        label.grid(sticky='w', row=4, column=0, padx=10,pady=10)
        sensor_entry.grid(sticky='w', row=4, column=1, pady=10)

        # Add Widgets to list
        self.widgets.append(sensor_entry)
    
    
    def add_separator(self, y_value, window):
        """Adds seperator line to window"""
        separator = ttk.Separator(window)
        # separator.grid(sticky="w", row=4, column=1, pady=10)
        separator.place(x=0, y=y_value, relwidth=1)
    
    def create_files_checkbox(self):
        """ Checkbox to create folders if the do not exist on user's filepath """
        checkbox = tk.Checkbutton(self.root, text="Create folders if they do not exist",
                                  variable=self.is_create_files, command=self.is_create_files.get())
        checkbox.grid(sticky="w", row=5, column=1, pady=30)
        # Add Widgets to list
        self.widgets.append(checkbox)

    def begin_test_btn(self):
        """ Opens dialog to verify settings before actually beginning tests """
        btn = tk.Button(self.root, text="Begin Test", command=self.open_settings)
        btn.grid(sticky="w", row=7, column=3)


        # Add Widgets to list
        self.widgets.append(btn)
        
    def create_pause_btn(self):
        """
        Pauses current run
        Checks if there is a test occuring before pausing
        If test is already paused, text changes to unpause test
        """
        self.pause_btn = tk.Button(self.root, text="Pause Run", 
                                   command=self._helper_pause,
                                   state=tk.DISABLED)
        self.pause_btn.grid(sticky="w", row=7, column=2)

    def create_analysis_btn(self):
        """
        Runs analysis script on current selected FUT folder
        """
        analysis_btn = tk.Button(self.root, text="Perform Analysis", 
                                   command=self.analysis_warning,
                                   state=tk.NORMAL)
        analysis_btn.grid(sticky="w", row=7, column=0, padx=10)
    
    def analysis_warning(self):
        """ Sends a warning to user that they should select a folder with FUT data before performing analysis 
            Aswell as make sure they have performed a test so there is data to analyze """
        self.warning("Please select a folder with FUT data and perform a test before running analysis.")
        # wait for wanring to be closed before allowing user to continue
        if self.is_warning_cancel.get() == 0:
            self.update_textbox(f"Performing analysis on sensor {self.sensor_id.get()} with sensor type {self.sensor_type.get()}...")
            self.perform_analysis()
            self.update_textbox(f"Analysis complete for sensor {self.sensor_id.get()}.")
        else:
            self.update_textbox(f"Analysis cancelled.")
        self.is_warning_cancel.set(0) # reset warning cancel variable for future use

    def _helper_pause(self, *args):
        if self.toggle_pause.get() == 0:
            self.toggle_pause.set(1)
        elif self.toggle_pause.get() == 1: # if test is Paused then unpause
            self.toggle_pause.set(0)
            self._EM_test()

    def update_pause_btn(self, *args):
        """ Updates pause text to be correct """
        if self.toggle_pause.get() == 0: # Test is not Paused
            self.pause_btn.config(text="Pause Run")
        else: # Test is Paused
            self.pause_btn.config(text="Unpause Run")

    def open_settings(self):
        """Opens a settings dialog window for test configuration"""
        SettingsWindow(self.root, self)

    """
    Dialogue(s) pop ups: Error, test complete, confirmations, etc.
    """
    def error(self, text):
        # Create a new top-level window
        error = tk.Toplevel(self.root)
        error.title("An Error Has Occured")
        error.geometry("500x200") 
        error.resizable(False, False)
        # Disable interaction with main window
        error.grab_set()

        # Heading
        heading_frame = tk.Frame(error, width=300, height=50)
        heading_frame.grid(sticky='w', row=1, pady=10)
        heading = tk.Label(heading_frame, 
                           text=f"{text}")
        heading.pack(padx=20, pady=20)

    def warning(self, text):
        def on_close():
            self.is_warning_cancel.set(0) # redundent, but useful for debugging
            warn.grab_release()
            warn.destroy()

        def on_cancel():
            self.is_warning_cancel.set(1)
            warn.grab_release()
            warn.destroy()

        # Create a new top-level window
        warn = tk.Toplevel(self.root)
        warn.title("Warning")
        warn.geometry("600x200") 
        warn.resizable(False, False)
        # Disable interaction with main window
        warn.grab_set()
        warn.protocol("WM_DELETE_WINDOW", on_close)

        # Heading
        heading_frame = tk.Frame(warn, width=300, height=50)
        heading_frame.grid(sticky='w', row=0, column=0, pady=10)
        heading = tk.Label(heading_frame, 
                           text=f"{text}")
        heading.pack(padx=20, pady=20)

        # Buttons
        exit_btn = tk.Button(warn, text="Ok", 
                             command=on_close, 
                             width=10, height=1)
        
        cancel_btn = tk.Button(warn, text="Cancel", 
                             command=on_cancel, 
                             width=10, height=1)
        
        exit_btn.grid(sticky='w', row=1, column=1, pady=65)
        cancel_btn.grid(sticky='w', row=1, column=0, padx=10, pady=65)
        self.add_separator(y_value=120, window=warn)
        # Pause main thread until action is done 
        self.root.wait_window(warn) 
    
    def perform_analysis(self,*args):
        """Runs analysis in a separate script"""
        test_type = self.test_type.get()
        sensor_type = self.sensor_type.get()
        if test_type == "EM":
            analysis = EMAnalysis(self.saved_path.get(), self.sensor_id.get(), sensor_type=sensor_type)
            analysis.save_data()
        elif test_type == "Shear":
            analysis = ShearAnalysis(self.saved_path.get(), self.sensor_id.get())
            analysis.run_full_analysis()

    def testing_complete(self):
        def new_test(*args):
            """Helper function to go back to testing window"""
            complete.grab_release()
            complete.withdraw()
        # Create a new top-level window
        complete = tk.Toplevel(self.root)
        complete.title("Testing complete")
        complete.geometry("650x150") 
        complete.resizable(False, False)
        # Disable interaction with main window
        complete.grab_set()

        # Heading
        heading_frame = tk.Frame(complete, width=300, height=50)
        heading_frame.grid(sticky='w', row=1, pady=10)
        sensor = self.sensor_id.get()
        heading = tk.Label(heading_frame, 
                           text=f"All Runs have been completed for sensor {sensor}.")
        heading.pack(padx=20, pady=20)
        self.add_separator(y_value=100, window=complete) # about every 50 px is a row
        # Buttons
        exit_btn = tk.Button(complete, text="Exit", 
                             command=self.root.destroy, 
                             width=10, height=1)
        test_btn = tk.Button(complete, text="New Test", 
                             command=new_test, 
                             width=10, height=1)
        analysis_btn = tk.Button(complete, text="Perform Analysis", 
                             command=self.perform_analysis, 
                             width=18, height=1)
        # Button arrangment
        exit_btn.grid(sticky='w', row=2, column=1, padx=5, pady=30)
        test_btn.grid(sticky='w', row=2, column=2, padx=5, pady=30)
        analysis_btn.grid(sticky='w', row=2, column=3, columnspan=2, padx=5, pady=30)

    def test_funct(self, n_runs, current_run, folder_path, sensor, zaber_comport):
        # Create a datetime object (e.g., the current date and time)
        # path = Path(self.saved_path.get())
        # file_name = "Run " + str(current_run) + ".xlsx" # create file name
        # path = path / file_name
        # force_readings = [1, 11, 213123, 1232, 121221]
        # workbook = xlsxwriter.Workbook(path)
        # worksheet = workbook.add_worksheet(str(current_run))
        
        # worksheet.write('A1', 'Index')
        # worksheet.write('B1', 'Load Cell')
        # for index in range(len(force_readings)):
        #     worksheet.write(index+1, 0, index + 1)
        #     worksheet.write(index+1, 1, force_readings[index])
        # workbook.close()
        cmd = [sys.executable, 'jlink.py', folder_path, str(current_run)] # this is the command to run the test script. The second argument is the path where the data will be saved, and the third argument is the run number
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        proc = subprocess.Popen(
        cmd,
        creationflags=creationflags,
        )

        try:
            sleep(1) # Give the subprocess a moment to start
        finally:
            print("Main Script starting")
            if current_run < n_runs:
                for i in range(1):
                    # Check if paused during the loop
                    if self.toggle_pause.get() == 1: 
                        self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                        
                        if self.is_warning_cancel.get() == 0:
                            return current_run # Return same run number to resume from where we left off
                        self.toggle_pause.set(0)
                    sleep(1)
                self.root.update()  # Keep GUI responsive
                if os.name == 'nt':
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate() # ends subprocess

                # now wait for subprocess to cleanup
                try:
                    proc.wait(timeout=10)
                    print("Subprocess exited cleanly")
                except subprocess.TimeoutExpired:
                    print("Subprocess took to long. Killing script")
                    proc.kill()
                return int(current_run) + 1
            elif current_run == n_runs:
                for i in range(1):
                    # Check if paused during the loop
                    if self.toggle_pause.get() == 1: 
                        return current_run # Return same run number to resume from where we left off
                    sleep(1)
                    self.root.update()  # Keep GUI responsive
                if os.name == 'nt':
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate() # ends subprocess

                # now wait for subprocess to cleanup
                try:
                    proc.wait(timeout=10)
                    print("Subprocess exited cleanly")
                except subprocess.TimeoutExpired:
                    print("Subprocess took to long. Killing script")
                    proc.kill()
                return int(current_run) + 1
    """
    Big Testing function
    """
    def run_tests(self, n_runs, current_run, zaber_comport):
        speed = 0.5          # speed of travel in mm/s
        upper_limit = 20     # Newtons
        Extract = 12.75      # initial travel distance before starting test cycle
        isNewerUSB225 = 1

        # Initial params per cycle
        init_force = 1
        force_readings = []
        timestamps = []
        init_val = 0
        force_idx = 0

        # ── Zaber setup ───────────────────────────────────────────────────────
        zaber = ZaberCLI()
        connection = zaber.connect(comport=zaber_comport)
        if connection == 0:
            print("Cannot Connect to Zaber comport")
            self.error("Cannot Connect to Zaber comport")
            return

        if zaber.axis.is_parked():
            zaber.axis.unpark()

        # Move 12.75 mm before cycle (keeps 1.5 mm gap between base and tip)
        zaber.axis.move_relative((Extract - 1.8), Units.LENGTH_MILLIMETRES)

        # Record position after the initial move
        currentPosition = zaber.axis.get_position()
        currentPosition_mm = (currentPosition * 0.047625) / 1000

        # ── FUTEK setup ───────────────────────────────────────────────────────
        futek = FUTEKDeviceCLI()

        # ── Launch JLink subprocess and sync shared t0 ────────────────────────
        proc, t0 = self._launch_jlink_and_sync(current_run)
        if proc is None:
            zaber.disconnect()
            return current_run   # retry this run number

        # ── Phase 1: Move actuator down until upper_limit is reached ─────────
        zaber.axis.move_velocity(speed * 0.1, Units.VELOCITY_MILLIMETRES_PER_SECOND)
        while True:
            if self.toggle_pause.get() == 1:
                self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                if self.is_warning_cancel.get() == 0:   # user pressed OK
                    zaber.axis.stop()
                    zaber.axis.wait_until_idle()
                    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
                    self._stop_jlink_subprocess(proc)
                    futek.stop()
                    futek.exit()
                    zaber.disconnect()
                    return current_run
                self.toggle_pause.set(0)                 # user pressed Cancel

            self.root.update()

            reading_force = futek.getNormalData()
            if isNewerUSB225:
                reading_force = reading_force * (-4.44822)  # lbf -> N, polarity flip

            if init_force:
                init_val = reading_force
                init_force = 0

            stage_force = reading_force - init_val
            force_readings.append(stage_force)
            timestamps.append(datetime.now().timestamp() - t0)
            print("Force Value: " + str(stage_force))

            if stage_force >= upper_limit:
                zaber.axis.stop()
                break

        # ── Phase 2: Move actuator back up to starting position ──────────────
        zaber.axis.move_velocity(-speed * 2, Units.VELOCITY_MILLIMETRES_PER_SECOND)
        while True:
            if self.toggle_pause.get() == 1:
                self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                if self.is_warning_cancel.get() == 0:   # user pressed OK
                    zaber.axis.stop()
                    zaber.axis.wait_until_idle()
                    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
                    self._stop_jlink_subprocess(proc)
                    futek.stop()
                    futek.exit()
                    zaber.disconnect()
                    return current_run
                self.toggle_pause.set(0)                 # user pressed Cancel

            self.root.update()

            reading_force = futek.getNormalData()
            if isNewerUSB225:
                reading_force = reading_force * (-4.44822)

            stage_force = reading_force - init_val
            force_readings.append(stage_force)
            timestamps.append(datetime.now().timestamp() - t0)

            curr_pos = zaber.axis.get_position()
            last_position = (curr_pos * 0.047625) / 1000
            if last_position <= (currentPosition * 0.047625) / 1000:
                zaber.axis.stop()
                break

        # ── Return to home position ───────────────────────────────────────────
        if zaber.axis.is_parked():
            zaber.axis.unpark()
        zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)

        # ── Stop JLink subprocess ─────────────────────────────────────────────
        self._stop_jlink_subprocess(proc)

        # ── Save data to Excel ────────────────────────────────────────────────
        path = Path(self.saved_path.get())
        file_name = "Run " + str(current_run) + ".xlsx"
        path = path / file_name
        workbook = xlsxwriter.Workbook(path)
        worksheet = workbook.add_worksheet(str(current_run))

        worksheet.write('A1', 'Index')
        worksheet.write('B1', 'Load Cell')
        worksheet.write('C1', 'Time')

        for index, (stage_force, timestamp) in enumerate(zip(force_readings, timestamps), start=1):
            worksheet.write(index, 0, index)
            worksheet.write(index, 1, stage_force)
            worksheet.write(index, 2, timestamp)
        workbook.close()

        futek.stop()
        futek.exit()
        zaber.disconnect()
        return int(current_run) + 1
    

    def _launch_jlink_and_sync(self, current_run):
        """Launches jlink.py, waits for JLINK_READY, sends back shared t0.
        Returns (proc, t0) on success, (None, None) on failure."""
        savepath = self.saved_path.get()
        cmd = [sys.executable, 'jlink.py', savepath, str(current_run)]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        proc = subprocess.Popen(
            cmd, creationflags=creationflags,
            stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True,
        )

        ready = False
        for line in proc.stdout:
            print("jlink subprocess:", line.strip())
            if line.strip() == "JLINK_READY":
                ready = True
                break
            if proc.poll() is not None:
                break

        if not ready:
            self.error("jlink subprocess failed to start / never became ready")
            return None, None

        t0 = datetime.now().timestamp()
        try:
            proc.stdin.write(f"{t0}\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.error("Failed to send t0 to jlink subprocess (pipe closed)")
            return None, None

        return proc, t0


    def _stop_jlink_subprocess(self, proc):
        if os.name == 'nt':
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10)
            print("Subprocess exited cleanly")
        except subprocess.TimeoutExpired:
            print("Subprocess took too long. Killing script")
            proc.kill()

    def run_triangle_test(self, current_run, zaber_comport, freq_hz=0.25,
                            lower_force_n=2.275, upper_force_n=3.575, cycle_count=25,
                            sample_rate_hz=100.0, max_velocity_mm_s=0.7):
            """
            Calibration pass: press in slowly and record the actuator depth at
            lower_force_n and upper_force_n (same single loading-curve calibration
            as the sine test - no hysteresis correction). The resulting depth range
            is used to back-calculate the constant velocity needed to complete one
            full up+down triangle cycle at freq_hz:
                v = 2 * (deep_depth - shallow_depth) * freq_hz
            The stage then drives at that fixed velocity, reversing direction each
            time the FUTEK reading crosses lower_force_n or upper_force_n (direct
            force-threshold reversal - no depth->force mapping needed at runtime).
            Sampled on an absolute-time schedule (no time.sleep) at sample_rate_hz.
            Logs commanded/derived velocity, actual position readback, and force.
            Uses the shared jlink handshake.
            """
            Extract = 12.75
            calib_speed = 0.1  # mm/s, slow and deliberate
            sample_dt = 1.0 / sample_rate_hz

            zaber = ZaberCLI()
            connection = zaber.connect(comport=zaber_comport)
            if connection == 0:
                print("Cannot Connect to Zaber comport")
                self.error("Cannot Connect to Zaber comport")
                return

            futek = FUTEKDeviceCLI()

            proc, t0 = self._launch_jlink_and_sync(current_run)
            if proc is None:
                zaber.disconnect()
                return current_run

            # approach the sensor, same as the threshold test
            zaber.axis.move_relative((Extract - 1.8), Units.LENGTH_MILLIMETRES)
            start_pos_mm = zaber.axis.get_position(Units.LENGTH_MILLIMETRES)

            if zaber.axis.is_parked():
                zaber.axis.unpark()

            # --- calibration press: find depth at lower_force_n and upper_force_n ---
            zaber.axis.move_velocity(calib_speed, Units.VELOCITY_MILLIMETRES_PER_SECOND)

            init_force = None
            prev_stage = None
            shallow_depth = None
            deep_depth = None
            cal_spike_threshold = (upper_force_n - lower_force_n) + 5.0

            while True:
                self.root.update()
                f = futek.getNormalData() * 4.44822
                if init_force is None:
                    init_force = f
                stage = abs(f - init_force)

                if prev_stage is not None and abs(stage - prev_stage) > cal_spike_threshold:
                    zaber.axis.stop()
                    self.error("Force spike during calibration - aborting triangle test")
                    self._stop_jlink_subprocess(proc)
                    futek.stop(); futek.exit(); zaber.disconnect()
                    return current_run
                prev_stage = stage

                depth = zaber.axis.get_position(Units.LENGTH_MILLIMETRES) - start_pos_mm
                if shallow_depth is None and stage >= lower_force_n:
                    shallow_depth = depth
                if stage >= upper_force_n:
                    deep_depth = depth
                    break

            zaber.axis.stop()
            zaber.axis.wait_until_idle()

            if shallow_depth is None or deep_depth is None:
                self.error("Calibration failed to reach both force bounds")
                self._stop_jlink_subprocess(proc)
                futek.stop(); futek.exit(); zaber.disconnect()
                return current_run

            cal_init = init_force

            # --- back-calculate velocity needed to hit freq_hz over this depth range ---
            depth_range = abs(deep_depth - shallow_depth)
            if depth_range <= 0:
                self.error("Calibration produced zero depth range - cannot derive velocity")
                self._stop_jlink_subprocess(proc)
                futek.stop(); futek.exit(); zaber.disconnect()
                return current_run

            velocity_mm_s = 2.0 * depth_range * freq_hz

            # sanity check against the stage's rated envelope, if provided
            if max_velocity_mm_s is not None and velocity_mm_s > max_velocity_mm_s:
                self.error(f"Derived velocity {velocity_mm_s:.3f} mm/s exceeds stage max "
                        f"{max_velocity_mm_s:.3f} mm/s for {freq_hz} Hz over {depth_range:.4f}mm - "
                        f"aborting before driving the stage")
                self._stop_jlink_subprocess(proc)
                futek.stop(); futek.exit(); zaber.disconnect()
                return current_run

            # --- drive in, find the lower threshold once to set the starting direction ---
            zaber.axis.move_velocity(velocity_mm_s, Units.VELOCITY_MILLIMETRES_PER_SECOND)
            spike_threshold = (upper_force_n - lower_force_n) + 5.0
            prev_force = None

            while True:
                self.root.update()
                f = futek.getNormalData() * 4.44822 - cal_init
                if prev_force is not None and abs(f - prev_force) > spike_threshold:
                    zaber.axis.stop()
                    self.error("Force spike while approaching lower threshold - aborting test")
                    self._stop_jlink_subprocess(proc)
                    futek.stop(); futek.exit(); zaber.disconnect()
                    return current_run
                prev_force = f
                if f >= lower_force_n:
                    break

            zaber.axis.stop()
            zaber.axis.wait_until_idle()

            # how long setup + calibration took, on the shared t0 clock
            test_start_offset = datetime.now().timestamp() - t0

            # --- bang-bang tracking loop at the derived velocity ---
            FORCE_CEILING_N = upper_force_n + 5.0
            total_reversals_needed = cycle_count * 2  # one full cycle = one up leg + one down leg

            force_readings = []
            timestamps = []
            position_readings = []      # actual Zaber position readback each tick
            direction_flags = []        # True = driving toward upper_force_n, False = toward lower
            missed_ticks = 0
            prev_force = None
            tripped = False
            reversal_count = 0
            loading = True  # we just arrived at lower threshold, now driving up

            zaber.axis.move_velocity(velocity_mm_s, Units.VELOCITY_MILLIMETRES_PER_SECOND)

            loop_start = time.time()
            next_tick = loop_start
            sample_idx = 0

            while True:
                if self.toggle_pause.get() == 1:
                    self.warning("Pausing mid-cycle isn't supported; stopping this run.")
                    zaber.axis.stop()
                    self.toggle_pause.set(0)
                    break
                self.root.update()

                now = time.time()
                if now < next_tick:
                    continue  # spin until next scheduled sample, stay GUI-responsive

                if reversal_count >= total_reversals_needed:
                    break

                if now - next_tick > sample_dt:
                    missed_ticks += 1

                t_elapsed = now - loop_start
                reading_force = futek.getNormalData() * 4.44822 - cal_init
                actual_pos = zaber.axis.get_position(Units.LENGTH_MILLIMETRES) - start_pos_mm

                # Safety: hard ceiling, or an implausible jump between samples
                if reading_force > FORCE_CEILING_N or (
                    prev_force is not None and abs(reading_force - prev_force) > spike_threshold
                ):
                    zaber.axis.stop()
                    self.error(f"Force exceeded safety ceiling ({reading_force:.2f} N) - triangle test stopped")
                    tripped = True
                    break
                prev_force = reading_force

                # reversal logic: driven directly by live force feedback
                if loading and reading_force >= upper_force_n:
                    zaber.axis.move_velocity(-velocity_mm_s, Units.VELOCITY_MILLIMETRES_PER_SECOND)
                    loading = False
                    reversal_count += 1
                elif (not loading) and reading_force <= lower_force_n:
                    zaber.axis.move_velocity(velocity_mm_s, Units.VELOCITY_MILLIMETRES_PER_SECOND)
                    loading = True
                    reversal_count += 1

                force_readings.append(reading_force)
                timestamps.append(datetime.now().timestamp() - t0)
                position_readings.append(actual_pos)
                direction_flags.append(loading)

                sample_idx += 1
                next_tick += sample_dt

            zaber.axis.stop()
            zaber.axis.wait_until_idle()
            zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)

            self._stop_jlink_subprocess(proc)

            if tripped:
                futek.stop(); futek.exit(); zaber.disconnect()
                return current_run  # discard run, don't save/increment on a safety abort

            # achieved frequency is an outcome even though we derived velocity from a
            # target - actual material response / control lag can still make it drift
            if reversal_count > 0 and timestamps:
                total_duration = timestamps[-1] - timestamps[0]
                achieved_freq_hz = reversal_count / 2.0 / total_duration if total_duration > 0 else float('nan')
            else:
                achieved_freq_hz = float('nan')

            path = Path(self.saved_path.get())
            file_name = f"Run {current_run} triangle.xlsx"
            path = path / file_name
            workbook = xlsxwriter.Workbook(path)
            worksheet = workbook.add_worksheet(str(current_run))
            worksheet.write('A1', 'Index')
            worksheet.write('B1', 'Load Cell - Actual (N)')
            worksheet.write('C1', 'Time (s)')                       # shared t0 clock — aligns with CAP file
            worksheet.write('D1', 'Time since test start (s)')      # 0-based at tracking start
            worksheet.write('E1', 'Actual Position (mm)')            # real Zaber readback, not commanded
            worksheet.write('F1', 'Direction (True=loading/up)')
            worksheet.write('G1', f'Velocity Setpoint (mm/s) [+/-{velocity_mm_s:.4f}, {lower_force_n}-{upper_force_n}N]')
            worksheet.write('H1', f'Target freq (Hz): {freq_hz}')
            worksheet.write('I1', f'Achieved freq (Hz, avg): {achieved_freq_hz:.4f}')
            worksheet.write('J1', f'Calibrated depth range (mm): {depth_range:.4f}')
            for index, (force, t, pos, direction) in enumerate(
                zip(force_readings, timestamps, position_readings, direction_flags), start=1
            ):
                worksheet.write(index, 0, index)
                worksheet.write(index, 1, force)
                worksheet.write(index, 2, t)
                worksheet.write(index, 3, t - test_start_offset)
                worksheet.write(index, 4, pos)
                worksheet.write(index, 5, direction)
                worksheet.write(index, 6, velocity_mm_s if direction else -velocity_mm_s)
            workbook.close()

            futek.stop()
            futek.exit()
            zaber.disconnect()
            return int(current_run) + 1

    def _create_widgets(self):
        self.display_updates()
        self.select_folder()
        self.enter_sensor_id()
        self.select_sensor_type()
        self.add_separator(y_value=310, window=self.root) # about every 50 px is a row
        self.create_files_checkbox()
        self.begin_test_btn()
        self.create_pause_btn()
        self.create_analysis_btn()
        self.navbar()

        self.is_test_started.trace('w', self.trace_test)
        self.toggle_pause.trace('w', self.trace_pause)

    def on_close(self):
        self.root.destroy()

main = MainWindow()
main.root.mainloop()
