import tkinter as tk
from tkinter import Tk
from tkinter import ttk
from tkinter import filedialog as fd
import numpy as np
import time
import xlsxwriter
from pathlib import Path
from datetime import datetime
# from zaber_cli import ZaberCLI
# from futek_cli import FUTEKDeviceCLI
# from zaber_motion import Units
from settings_window import SettingsWindow
from shear_window import ShearWindow
from analysis_window import AnalysisWindow
from eb_analysis import Analysis
class MainWindow(tk.Frame):
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
        self.is_create_files = tk.BooleanVar(value=1) # this is boolean
        self.is_pause_between_runs = tk.BooleanVar(value=1) # this is boolean
        self.is_test_started = tk.BooleanVar(value=0) # this is boolean

        # Track the current run
        self.n_runs = tk.IntVar(value=3)
        self.current_run = tk.IntVar(value=1)
        
        # Comports have default values
        self.zaber_comport = tk.StringVar(value="COM3")

        # EB, Shear etc.
        self.test_type = tk.StringVar(value="EB")

        # surface area of eco block ie 325mm2, 50.27, etc.
        self.surface_area = tk.StringVar(value="325mm2")

        """
        These variables control the state of the test ie pauses, stops, recalibrations
        """
        self.textbox = None
        self.pause_btn = None
        self.toggle_pause = tk.BooleanVar(value=0) # this is boolean, paused=1, not paused=0
        self.is_warning_cancel = tk.BooleanVar(value=0) # this is for pause warning currently during EB test
        self.widgets = [] # when testing starts, these widgets will all get disabled

        self._create_widgets()


    def display_updates(self):
        """ Display updates about current run progress """
        textbox = tk.Text(self.root, 
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

            if test_type == "EB":
                self.pause_btn.config(state=tk.NORMAL)
                self._eb_test()
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

    def _eb_test(self):
        """ Helper function to continue test if conditions are met """
        if not (self.is_test_started.get() and self.toggle_pause.get() == 0):
            return
        
        n_runs = self.n_runs.get()
        current_run = self.current_run.get()
        
        # Run Test function and update textbox according to progress
        self.update_textbox(f"Beginning run {current_run}")
        state = self.test_funct(n_runs, current_run, self.saved_path.get(), 
                                self.sensor_id.get(), self.zaber_comport.get())
        
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
        self.saved_path.set("")
        self.sensor_id.set("")

    """
    GUI Widgets that remain mostly the same during testing
    """
    def navbar(self):
        def open_analysis():
            analysis = AnalysisWindow(self.root, self)
        frame = tk.Frame(self.root, bg="lightblue", width=625, height=100, bd=3, relief=tk.RIDGE)
        frame.grid(sticky='ew', row=0, column=0, columnspan=4, rowspan=1)
        self.root.grid_rowconfigure(0, weight=1)

        # Navigation buttons
        main_btn = tk.Button(self.root, text='Analysis', command=open_analysis)

        # Layout
        main_btn.grid(sticky='w', row=0, column=0)
        
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
        # Add Widgets to list
        self.widgets.append(checkbox)

    def begin_test_btn(self):
        """ Opens dialog to verify settings before actually beginning tests """
        btn = tk.Button(self.root, text="Begin Test", command=self.open_settings)
        btn.grid(sticky="w", row=6, column=3)


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
        self.pause_btn.grid(sticky="w", row=6, column=2)

    def _helper_pause(self, *args):
        if self.toggle_pause.get() == 0:
            self.toggle_pause.set(1)
        elif self.toggle_pause.get() == 1: # if test is Paused then unpause
            self.toggle_pause.set(0)
            self._eb_test()

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
    
    def testing_complete(self):
        def new_test(*args):
            """Helper function to go back to testing window"""
            complete.grab_release()
            complete.withdraw()
        def perform_analysis(*args):
            """Runs analysis in a separate script"""
            analysis = Analysis(self.saved_path.get(), self.sensor_id.get(), sensor_type=3)
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
                             command=perform_analysis, 
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
        
        if current_run < n_runs:
            for i in range(1):
                # Check if paused during the loop
                if self.toggle_pause.get() == 1: # TODO: Right here, we call recalibration script
                    self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                    
                    if self.is_warning_cancel.get() == 0:
                        return current_run # Return same run number to resume from where we left off
                    self.toggle_pause.set(0)
                time.sleep(1)
                self.root.update()  # Keep GUI responsive
            return int(current_run) + 1
        elif current_run == n_runs:
            for i in range(1):
                # Check if paused during the loop
                if self.toggle_pause.get() == 1:  # TODO: Right here, we call recalibration script
                    return current_run # Return same run number to resume from where we left off
                time.sleep(1)
                self.root.update()  # Keep GUI responsive
            return int(current_run) + 1
    """
    Big Testing function
    """
    def run_tests(self, n_runs, current_run, zaber_comport):
        speed = 0.5 # speed of travel in mm/s (millimeter/second)
        upper_limit = 20 # 32 Newtons
        Extract = 12.75 # initial travel distance before starting test cycle
        isNewerUSB225 = 1 #### do we need this?

        # Zaber setup
        zaber = ZaberCLI()
        connection = zaber.connect(comport=zaber_comport)
        if connection == 0:
            print("Cannot Connect to Zaber comport")
            self.error("Cannot Connect to Zaber comport")
            return 
        # Futek Load Cell setup
        futek = FUTEKDeviceCLI()

        # Move 12.75 before cycle
        # Keep constant:setting gap distance between base with sensor to tip to 1.5mm
        zaber.axis.move_relative((Extract-1.8), Units.LENGTH_MILLIMETRES)

        # Display current position in mm after relative move
        currentPosition = zaber.axis.get_position()
        currentPosition_mm = (currentPosition*0.047625)/1000
        #print(f"Current Position is: {currentPosition_mm:.2f} mm \n")


        #Initial params per cycle
        init_force = 1
        force_readings = [0] * 12000 # 1-D array of zeros
        init_time = datetime.now()
        init_seconds = init_time.second + init_time.microsecond / 1e6

        if zaber.axis.is_parked():
            zaber.axis.unpark()
        # Move actuator down
        zaber.axis.move_velocity(speed*0.1, Units.VELOCITY_MILLIMETRES_PER_SECOND)
        init_val = 0 # initial value for force
        force_idx = 0
        while True:
            # Check if paused during the loop
            if self.toggle_pause.get() == 1: # TODO: Right here, we call recalibration script
                self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                
                if self.is_warning_cancel.get() == 0: # User pressed OK
                    zaber.axis.stop()
                    zaber.axis.wait_until_idle()
                    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
                    futek.stop()
                    futek.exit()
                    zaber.disconnect()
                    return current_run  # Return same run number to resume from where we left off
                self.toggle_pause.set(0) # User pressed Cancel
            self.root.update()  # Keep GUI responsive

            reading_force = futek.getNormalData() # Read force value

            if isNewerUSB225:
                reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity

            if init_force: # Verify initial values
                init_val = reading_force # TODO: There should be an easier way than this flag
                init_force = 0
            
            # Take the residual of the current force vs inital one
            # Store residual in force_readings and print out residual
            stage_force = reading_force - init_val
            force_readings[force_idx] = stage_force
            force_idx = force_idx + 1
            #print("Force Value: " + str(stage_force))

            # Once sample is hit, stop the axis
            if stage_force >= upper_limit:
                zaber.axis.stop()
                break
        
        # Move actuator back up
        zaber.axis.move_velocity(-speed*2, Units.VELOCITY_MILLIMETRES_PER_SECOND)
        while True:
            # Check if paused during the loop
            if self.toggle_pause.get() == 1: # TODO: Right here, we call recalibration script
                self.warning("Warning: Pausing this run will recalibrate the zaber machine and reset the current run.")
                
                if self.is_warning_cancel.get() == 0:
                    zaber.axis.stop()
                    zaber.axis.wait_until_idle()
                    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
                    futek.stop()
                    futek.exit()
                    zaber.disconnect()
                    return current_run  # Return same run number to resume from where we left off
                self.toggle_pause.set(0)
            self.root.update()  # Keep GUI responsive

            reading_force = futek.getNormalData()

            if isNewerUSB225:
                reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity

            # Take the residual of the current force vs inital one
            # Store residual in force_readings and print out residual
            stage_force = reading_force - init_val
            force_readings[force_idx] = stage_force
            force_idx = force_idx + 1
            #print("Force Value: " + str(stage_force))

            # Grab current position
            curr_pos = zaber.axis.get_position()
            last_position = (curr_pos*0.047625)/1000
            #print("Position: " + str(last_position))
            if last_position <= (currentPosition*0.047625)/1000:
                zaber.axis.stop()
                break

        # move back to original position
        if zaber.axis.is_parked():
            zaber.axis.unpark()
        zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
        #print("Run " + str(run_idx) + " completed")

        # Save data to run file
        # We could make this a separate function
        path = Path(self.saved_path.get())
        file_name = "Run " + str(current_run) + ".xlsx" # create file name
        path = path / file_name
        workbook = xlsxwriter.Workbook(path)
        worksheet = workbook.add_worksheet(str(current_run))

        # Create Column headers
        worksheet.write('A1', 'Index')
        worksheet.write('B1', 'Load Cell')
        worksheet.write('C1', 'Time')

        # create time array

        time = np.linspace(init_seconds, 
                        (len(force_readings)- 1) * 0.016 + init_seconds,
                        len(force_readings))
        
        # Save data arrays to file
        for index in range(len(force_readings)):
            worksheet.write(index+1, 0, index + 1)
            worksheet.write(index+1, 1, force_readings[index])
            worksheet.write(index+1, 2, time[index])
        workbook.close()

        # Pause current run, reset sensor position manually and press enter to go to next run
        # if(current_run != n_runs):
            #zaber.axis.move_relative((Extract-1.8), Units.LENGTH_MILLIMETRES)
        futek.stop()
        futek.exit()
        zaber.disconnect()
        return int(current_run) + 1

    def _create_widgets(self):
        self.display_updates()
        self.select_folder()
        self.enter_sensor_id()
        self.add_separator(y_value=310, window=self.root) # about every 50 px is a row
        self.create_files_checkbox()
        self.begin_test_btn()
        self.create_pause_btn()
        # self.navbar()

        self.is_test_started.trace('w', self.trace_test)
        self.toggle_pause.trace('w', self.trace_pause)

main = MainWindow()
main.root.mainloop()
