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
        self.curr_xlim = 2
        self.ax.set_ylim(-0.5, self.curr_xlim)
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

        # Pack all widgets
        self.exit_btn.pack(side=tk.BOTTOM, pady=10, padx=10)
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


        # Initialize Load Cell and read initial values
        # self.futek = FUTEKDeviceCLI()
        reading_force = 0 # self.futek.getNormalData() 
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
        self.anim = FuncAnimation(self.fig, self.update_plot, interval=50, blit=False)
        
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
        reading_force = 0 # self.futek.getNormalData() 
       #reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        stage_force = reading_force - self.init_val

        # Append force readings to y axis
        #self.force_readings[current_time] = stage_force
        self.force_readings.append(stage_force)

        # Update line data
        self.line.set_data(self.time_readings, self.force_readings)
        
        # Recalculate data limits and autoscale
        self.curr_xlim += 0.07
        self.ax.set_xlim(0, self.curr_xlim)
        #self.ax.autoscale_view(scalex=True, scaley=True)

        return self.line,

    def save(self):
        """ Save plot aswell and related tables """
        save_path = self.main_window.saved_path.get()
        sensor_id = self.main_window.sensor_id.get()
        save_path = Path(save_path)
        self.fig.savefig(f'{save_path.parent}/Raw Fig_Shearing.png')

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