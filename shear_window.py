import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import matplotlib.ticker as ticker

import tkinter as tk
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.figure import Figure
from matplotlib.animation import FuncAnimation
import numpy as np
from datetime import datetime
# from futek_cli import FUTEKDeviceCLI
from pathlib import Path
import xlsxwriter
"""
Window for Shear testing live graph
TODO: Add option to stop and save the graph
OR just save the graph data once the window closes, including the entire plot
"""
class ShearWindow(tk.Toplevel):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.title("Live Sensor Data")
        self.geometry("800x600")
        self.main_window = main_window
        
        # Initial vars for plotting load cell data
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot([], [], 'r-', lw=2)
        self.ax.set_xlim(left=0, right=10)  # Set initial right limit, will autoscale
        self.curr_xlim = 10
        self.curr_ylim = 10
        self.curr_ylim_min = -0.5
        self.ax.set_ylim(self.curr_ylim_min, self.curr_ylim)
        self.ax.set_xlabel("Time Elapsed (seconds)")
        self.ax.set_ylabel("Force (N)")
        
        # Format x-axis to show MM:SS format
        def format_time(x, pos):
            minutes = int(x // 60)
            seconds = int(x % 60)
            return f"{minutes}:{seconds:02d}"
        self.ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_time))

        # This connects Matplotlib and tkinter together
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()

        # Create navigation toolbar for matplotlib
        self.toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.update()

        # Create an end test button
        self.exit_btn = tk.Button(self, text="Save and Exit", 
                             command=self.on_close, 
                             width=15, height=1)
        
        # Create a number input box for number of seconds to show on the x-axis
        self.last_seconds = tk.IntVar(value=15)
        # Put the label and entry in their own frame so they sit side-by-side
        self.seconds_frame = tk.Frame(self)
        self.seconds_label = tk.Label(self.seconds_frame, text="Seconds to Display:")
        self.seconds_entry = tk.Entry(self.seconds_frame, textvariable=self.last_seconds, width=10)

        # Create a checkbox for showing cumulative time
        self.is_checked = tk.BooleanVar()
        self.cumulative_btn = tk.Checkbutton(self.seconds_frame, text="Cumulative Time",
                                      variable=self.is_checked,
                                        width=15, height=1)
        
        # Entry to choose how large the axis is scaled
        self.yaxis_entry_label = tk.Label(self.seconds_frame, text="Y-Axis Limit:")
        self.yaxis_max_entry = tk.Entry(self.seconds_frame, width=10)
        self.yaxis_max_entry.insert(0, str(self.curr_ylim))

        self.yaxis_min_entry_label = tk.Label(self.seconds_frame, text="Y-Axis Min:")
        self.yaxis_min_entry = tk.Entry(self.seconds_frame, width=10)
        self.yaxis_min_entry.insert(0, str(self.curr_ylim_min))
        
        # Pack all widgets
        self.exit_btn.pack(side=tk.BOTTOM, pady=10, padx=10)
        self.cumulative_btn.pack(side=tk.RIGHT, padx=10)
        self.seconds_frame.pack(side=tk.BOTTOM, pady=5, padx=5)
        self.seconds_label.pack(side=tk.LEFT, padx=(0, 5))
        self.seconds_entry.pack(side=tk.LEFT)
        self.yaxis_max_entry.pack(side=tk.RIGHT, pady=5, padx=5)
        self.yaxis_entry_label.pack(side=tk.RIGHT, pady=5, padx=5)
        self.yaxis_min_entry.pack(side=tk.RIGHT, pady=5, padx=5)
        self.yaxis_min_entry_label.pack(side=tk.RIGHT, pady=5, padx=5)
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


        # Initialize Load Cell and read initial values
        #self.futek = FUTEKDeviceCLI()
        reading_force = 0 #self.futek.getNormalData() 
        #reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        self.init_val = reading_force 
        self.init_force = 0
        self.force_readings = []

        # Find Current Time
        self.init_time = datetime.now()
        self.time_readings = []
        self.date_readings = []
        # Starts graphing animation
        # Storing in 'self.anim' prevents garbage collection
        self.anim = FuncAnimation(self.fig, lambda frame: self.update_plot(frame), interval=50, blit=False)
        
        # On close of window behavior
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def update_plot(self, frame):
        """ 
        This function will display the data live on the screen 
        Y-Axis: Output of load cell in Newtons
        X-Axis: Time Elapsed
        """
        
        current_time = datetime.now()
        date_string = f'{current_time:%Y-%m-%d %H:%M:%S}'
        self.date_readings.append(date_string)
        elapsed_time = (current_time - self.init_time).total_seconds()
        self.time_readings.append(elapsed_time)
        # Read force values on load cell
        reading_force = 0 #self.futek.getNormalData() 
       #reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        stage_force = reading_force - self.init_val

        # Append force readings to y axis
        #self.force_readings[current_time] = stage_force
        self.force_readings.append(stage_force)

        # Update line data
        self.line.set_data(self.time_readings, self.force_readings)
        
        # Update Y-axis limit if changed
        try:
            new_ylim = float(self.yaxis_max_entry.get())
            new_ylim_min = float(self.yaxis_min_entry.get())
            self.curr_ylim = new_ylim
            self.curr_ylim_min = new_ylim_min
            self.ax.set_ylim(self.curr_ylim_min, self.curr_ylim)
        except ValueError:
            pass  # If conversion fails, keep current ylim
        
        # Update X-axis limit based on checkbox and entry
        if self.is_checked.get():
            # Recalculate data limits and autoscale
            self.curr_xlim += elapsed_time * 0.005
            self.ax.set_xlim(0, self.curr_xlim)
            #self.ax.autoscale_view(scalex=True, scaley=True)
        else:
            # If sliding display is unchecked, adjust x-axis limits to show only the last 15 seconds
            sec = self.seconds_entry.get()  # Update the value of last_seconds from the entry box
            try:
                sec = int(sec)
            except ValueError:
                sec = 15  # Default to 15 seconds if invalid input
            if elapsed_time > sec:
                self.ax.set_xlim(elapsed_time - sec, elapsed_time)
            else:
                self.ax.set_xlim(0, sec)

        return self.line,

    def save(self):
        """ Save plot aswell and related tables """
        save_path = self.main_window.saved_path.get()
        sensor_id = self.main_window.sensor_id.get()
        save_path = Path(save_path)
        self.fig.savefig(f'{save_path.parent}/DataPlot.png')

        date = datetime.now()
        am_pm = date.strftime('%p')
        filename = f"Live Graph_{date.month}-{date.day}-{date.year}_{date.hour}-{date.minute}-{date.second}-{am_pm}.xlsx"
        workbook = xlsxwriter.Workbook(save_path / filename)
        worksheet = workbook.add_worksheet(f"{sensor_id}")

        # Create Column headers
        worksheet.write('A1', 'Sample Number')
        worksheet.write('B1', 'Tracking Value')
        worksheet.write('C1', 'Date')
        worksheet.write('D1', 'Time Elapsed')

        for index in range(len(self.force_readings)):
            worksheet.write(index+1, 0, index + 1)
            worksheet.write(index+1, 1, self.force_readings[index])
            worksheet.write(index+1, 2, self.date_readings[index])
            worksheet.write(index+1, 3, self.time_readings[index])
        
        workbook.close()
    
    def on_close(self):
        print("saving and closing")
        self.save()
        # self.futek.stop()
        # self.futek.exit()
        self.main_window._end_testing()
        self.anim.event_source.stop()
        self.destroy()