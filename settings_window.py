import tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime
import serial.tools.list_ports

class SettingsWindow(tk.Toplevel):
    """Dialog window for verifying and configuring test settings"""
    
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.title("Verify Settings")
        self.geometry("300x400")
        self.resizable(False, False)
        self.grab_set()
        
        self.main_window = main_window
        self.widgets = []
        
        self._create_heading()
        self._add_separator(y_value=90)
        self._create_test_selection()
        self._create_num_runs()
        self._create_pause_checkbox()
        self._create_comport_selection()
        self._add_separator(y_value=250)
        self._create_begin_button()
    
    def _create_heading(self):
        """Create the heading frame and label"""
        heading_frame = tk.Frame(self, width=300, height=50)
        heading_frame.grid(sticky='w', row=1, pady=10)
        heading = tk.Label(heading_frame, 
                           text="Verify settings before beginning tests. \n"
                           "You cannot move on until all settings are filled in.")
        heading.pack(padx=10, pady=20)
    
    def _create_test_selection(self):
        """Selection box for different available tests (EB, Shear)"""
        def on_test_select(event):
            selected_item = test_combobox.get()
            test_combobox.set(selected_item)
            self.main_window.test_type.set(selected_item)
            
            # Disable other widgets if Shear is selected
            if selected_item == "Shear":
                for w in self.widgets:
                    w.config(state=tk.DISABLED)
            else:
                for w in self.widgets:
                    w.config(state=tk.NORMAL)
        
        test_label = tk.Label(self, text="Test Type:")
        test_combobox = ttk.Combobox(self, values=['EB', 'Shear'],
                                      state='readonly', textvariable=self.main_window.test_type)
        test_combobox.set('EB')
        test_combobox.bind("<<ComboboxSelected>>", on_test_select)
        test_label.grid(sticky='w', row=2, column=0, padx=10, pady=10)
        test_combobox.grid(sticky='w', row=2, column=0, padx=125, pady=10)
    
    def _create_num_runs(self):
        """Prompt user to enter number of runs during testing"""
        label = tk.Label(self, text="Number of Runs:")
        runs_entry = tk.Spinbox(self, from_=1, to=10, 
                                textvariable=self.main_window.n_runs, width=10)
        label.grid(sticky='w', row=3, column=0, padx=10, pady=10)
        runs_entry.grid(sticky='w', row=3, column=0, padx=125, pady=10)
        self.widgets.append(runs_entry)
    
    def _create_comport_selection(self):
        """Selection box for zaber comports"""
        zaber_label = tk.Label(self, text="Zaber Comport:")
        zaber_combobox = ttk.Combobox(self, 
                                       values=[port.device for port in serial.tools.list_ports.comports()],
                                       state='readonly', textvariable=self.main_window.zaber_comport)
        zaber_combobox.set('Select Comport')
        zaber_label.grid(sticky='w', row=4, column=0, padx=10, pady=10)
        zaber_combobox.grid(sticky='w', row=4, column=0, padx=125, pady=10)
        self.widgets.append(zaber_combobox)
    
    def _create_pause_checkbox(self):
        """Checkbox for pausing between runs"""
        checkbox = tk.Checkbutton(self, text="Pause between Runs?",
                                  variable=self.main_window.is_pause_between_runs,
                                  command=self.main_window.is_pause_between_runs.get())
        checkbox.grid(sticky="w", row=5, column=0, padx=10)
        self.widgets.append(checkbox)
    
    def _create_begin_button(self):
        """Button to begin the test"""
        def on_begin_clicked():
            sensor = self.main_window.sensor_id.get()
            saved_path = self.main_window.saved_path.get()
            test = self.main_window.test_type.get()
            
            if self.main_window.is_create_files.get():
                now = datetime.now()
                year = str(now.year)[2:]
                month = str(now.month).zfill(2)
                day = str(now.day).zfill(2)
                
                date_test_dir = f"{month} {day} {year}_325mm2_{test}"
                full_dir_path = Path(saved_path) / sensor / date_test_dir / "FUT"
                
                try:
                    full_dir_path.mkdir(parents=True, exist_ok=True)
                    self.main_window.saved_path.set(str(full_dir_path))
                    self._close_and_start()
                except OSError as e:
                    self.main_window.error(f"Error creating directory {full_dir_path}: {e}")
                    print(f"Error creating directory {full_dir_path}: {e}")
            else:
                self._close_and_start()
        
        btn = tk.Button(self, text="Begin Test", command=on_begin_clicked)
        btn.grid(sticky="w", row=6, column=0, padx=215, pady=115)
    
    def _close_and_start(self):
        """Close dialog and start the test"""
        self.grab_release()
        self.withdraw()
        self.main_window.pause_btn.config(state=tk.NORMAL)
        self.main_window.is_test_started.set(1)
    
    def _add_separator(self, y_value):
        """Add a separator line to the dialog"""
        separator = ttk.Separator(self)
        separator.place(x=0, y=y_value, relwidth=1)

